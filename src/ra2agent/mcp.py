"""MCP 服务：把指挥层的四个工具暴露给 DSH。

JSON-RPC 2.0，stdio 传输，一行一条消息；只用标准库（本项目不装第三方包）。

**启动时不连接游戏。** DSH 会先用一个临时探针进程列工具，那时游戏可能没开；
真正的连接在第一次调用工具时建立，随后由后台线程按约 2 Hz 推进技法层。

stdout 只放协议消息，日志一律走 stderr，否则会污染流。
"""
import json
import sys
import threading
import time

from . import __version__
from .client import Client
from .command import CallRequest, Commander
from .errors import Ra2Error
from .executor import Executor
from .intents import DecisionLog
from .micro import MicroLayer
from .observation import Observer
from .tactics import TacticPolicy, TacticRegistry
from .validate import Validator

#: 本服务认得的协议版本，第一条为最新。客户端报了认得的版本就照它回。
#: DSH 用的 SDK 只认 2026-07-28 与 2025-11-25；它走 legacy 握手时 offer 后者，
#: 若服务端回一个不在它 legacy 列表里的版本，连接会被拒。
PROTOCOL_VERSIONS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26",
                     "2024-11-05")
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]
#: 客户端报的版本不认识时回哪个。必须回 legacy 里最新的那个，不能回 LATEST：
#: legacy 握手只接受 pre-2026-07-28 的版本。
FALLBACK_PROTOCOL = "2025-11-25"

SERVER_NAME = "ra2agent"
#: 进系统提示的说明，尽量短。
INSTRUCTIONS = (
    "红警 2 对局工具。四个工具：status 读局势（每次醒来先看它，新结果与告警只报一次）、"
    "tactics 读当前可用的技法卡片、call 下达任务（立刻返回受理结果，生效与否之后用 "
    "status 看）、cancel 撤销在管任务。任何动作都必须经过技法，没有直接向引擎下命令的"
    "工具；单位一律用 status 里给出的 id。"
)

#: 每 tick 之间的秒数。约 2 Hz：单帧观测 11.9 KB，逐帧轮询不值。
TICK_INTERVAL = 0.5

TOOLS = (
    {
        "name": "status",
        "description": "读局势：一行摘要、在管任务、以及上次读过之后的新结果与告警。"
                       "每次醒来先读它；新结果只报一次。",
        "inputSchema": {"type": "object", "properties": {},
                        "additionalProperties": False},
    },
    {
        "name": "tactics",
        "description": "读当前可用的技法卡片（名字、说明、参数、适用条件）。"
                       "只列出此刻用得上的；可用 query 按名字或说明做子串筛选。",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string",
                                     "description": "可选，按关键词筛卡片"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "call",
        "description": "下达任务，立刻返回受理结果，不等待生效。批量下达时每条独立受理，"
                       "允许部分成功；是否成功由之后的 status 报。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "calls": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tactic": {"type": "string", "description": "技法名"},
                            "units": {"type": "array", "items": {"type": "integer"},
                                      "description": "作用对象，用 status 里的单位 id"},
                            "params": {"type": "object", "description": "技法参数"},
                            "ttl_frames": {"type": "integer",
                                           "description": "可选，多少帧后自动到期"},
                        },
                        "required": ["tactic"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["calls"],
            "additionalProperties": False,
        },
    },
    {
        "name": "cancel",
        "description": "撤销在管任务，交还它占用的单位。",
        "inputSchema": {
            "type": "object",
            "properties": {"intent_ids": {"type": "array", "items": {"type": "string"}}},
            "required": ["intent_ids"],
            "additionalProperties": False,
        },
    },
)

#: JSON-RPC 错误码
PARSE_ERROR, INVALID_REQUEST = -32700, -32600
METHOD_NOT_FOUND, INVALID_PARAMS = -32601, -32602
INTERNAL_ERROR = -32603


class GameSession:
    """与游戏的一条会话：懒连接，一个后台线程推进技法层。

    连接由本进程独占；`Client` 非线程安全，故所有访问都在同一把锁下。
    """

    def __init__(self, host=None, port=None, log_path=None,
                 tick_interval=TICK_INTERVAL, on_log=None):
        self.host = host
        self.port = port
        self.log_path = log_path
        self.tick_interval = tick_interval
        self.on_log = on_log
        self._lock = threading.RLock()
        self._client = None
        self._observer = None
        self._layer = None
        self._commander = None
        self._log = None
        self._observation = None
        self._stop = threading.Event()
        self._thread = None
        self._last_error = ""

    # ------------------------------------------------------------ 生命周期
    def ensure(self):
        """确保已连接并已启动推进线程；已连则直接返回。"""
        with self._lock:
            if self._client is not None:
                return self
            self._connect()
            return self

    def _connect(self):
        """连游戏、取底图与类型表、建技法层，并起后台线程。"""
        from .constants import DEFAULT_HOST, DEFAULT_PORT
        client = Client(self.host or DEFAULT_HOST, self.port or DEFAULT_PORT)
        client.connect()
        observer = Observer(client).bootstrap()
        registry = TacticRegistry(TacticPolicy.load("config/tactics.json")).load_builtin()
        log = DecisionLog(self.log_path) if self.log_path else None
        executor = Executor(client, observer.identity, types=observer.types,
                            validator=Validator(observer.map_data), log=log,
                            read_state=lambda: observer.poll().state)
        layer = MicroLayer(observer, registry, executor, log=log)
        self._client, self._observer, self._layer = client, observer, layer
        self._commander = Commander(layer, observer, log=log)
        self._log = log
        self._observation = observer.poll()
        self._emit("已连接游戏：帧 %d，地图 %dx%d，技法 %d 条，库指纹 %s"
                   % (self._observation.frame, observer.map_data.width,
                      observer.map_data.height, len(registry), registry.fingerprint()))
        self._stop.clear()
        self._thread = threading.Thread(target=self._tick_forever,
                                        name="ra2-tick", daemon=True)
        self._thread.start()

    def _tick_forever(self):
        """后台推进：每 tick 跑一次技法层。失焦或崩溃只记事件，不退出。"""
        while not self._stop.wait(self.tick_interval):
            with self._lock:
                if self._layer is None:
                    return
                try:
                    self._layer.tick()
                    self._observation = self._observer.observe()
                except Ra2Error as error:
                    self._fail(str(error))
                except OSError as error:
                    self._fail(f"连接出错：{error}")

    def close(self):
        """停线程、关连接。"""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            if self._client is not None:
                self._client.close()
            if self._log is not None:
                self._log.close()
            self._client = self._observer = self._layer = None
            self._commander = None
            self._log = None
            self._observation = None

    # ------------------------------------------------------------ 工具
    def call_tool(self, name, arguments) -> str:
        """执行一个工具，返回给模型的文本。出错抛 `Ra2Error` 或 `ValueError`。"""
        self.ensure()
        with self._lock:
            if name == "status":
                return self._commander.status(self._observation).render()
            if name == "tactics":
                cards = self._commander.tactics(arguments.get("query"),
                                                self._observation)
                if not cards:
                    return "此刻没有可用技法"
                return "\n".join(card.text() for card in cards)
            if name == "call":
                return self._call(arguments)
            if name == "cancel":
                return Commander.render_cancels(
                    self._commander.cancel(arguments["intent_ids"]))
        raise ValueError(f"没有这个工具：{name}")

    def _call(self, arguments) -> str:
        """把工具参数翻成 `CallRequest`，逐条下达。"""
        requests = []
        for index, item in enumerate(arguments["calls"]):
            if not isinstance(item, dict) or "tactic" not in item:
                raise ValueError(f"第 {index + 1} 条缺少 tactic")
            unknown = set(item) - {"tactic", "units", "params", "ttl_frames"}
            if unknown:
                raise ValueError(f"第 {index + 1} 条有不认识的字段：{sorted(unknown)}")
            requests.append(CallRequest(
                tactic=item["tactic"], units=tuple(item.get("units") or ()),
                params=item.get("params") or {}, ttl_frames=item.get("ttl_frames")))
        results = self._commander.call(requests, self._observation)
        return "\n".join(result.render() for result in results)

    def tool_names(self) -> tuple:
        """本服务暴露的工具名。"""
        return tuple(tool["name"] for tool in TOOLS)

    # ------------------------------------------------------------ 内部
    def _fail(self, detail) -> None:
        """记一次失败；连接断了就下次重连。"""
        if detail != self._last_error:
            self._last_error = detail
            self._emit(f"运行时出错：{detail}")

    def _emit(self, text) -> None:
        """往 stderr 写一行，给 DSH 的日志看。"""
        if self.on_log is not None:
            self.on_log(text)
            return
        print(f"[ra2agent] {text}", file=sys.stderr, flush=True)


class McpServer:
    """stdio 上的 MCP 服务器：一行一条 JSON-RPC 消息。"""

    def __init__(self, session, stdin=None, stdout=None):
        self.session = session
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self._initialized = False

    # ------------------------------------------------------------ 主循环
    def serve_forever(self):
        """读到 EOF 就退出。"""
        for line in self.stdin:
            line = line.strip()
            if not line:
                continue
            response = self.handle_line(line)
            if response is not None:
                self._write(response)

    def handle_line(self, line):
        """处理一行；返回要发回去的响应，通知或空行返回 `None`。"""
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            return _error(None, PARSE_ERROR, "不是合法的 JSON")
        if not isinstance(message, dict):
            return _error(None, INVALID_REQUEST, "消息必须是对象")
        return self.handle(message)

    def handle(self, message) -> dict:
        """处理一条消息。"""
        method = message.get("method")
        identifier = message.get("id")
        if method is None:
            return _error(identifier, INVALID_REQUEST, "缺少 method")
        if identifier is None:
            # 通知，不需要响应
            self._notify(method, message.get("params") or {})
            return None
        try:
            result = self._dispatch(method, message.get("params") or {})
        except _MethodError as error:
            return _error(identifier, error.code, str(error))
        except Exception as error:                     # 兜底：不让服务倒下
            return _error(identifier, INTERNAL_ERROR, f"{type(error).__name__}: {error}")
        return {"jsonrpc": "2.0", "id": identifier, "result": result}

    # ------------------------------------------------------------ 方法
    def _notify(self, method, params) -> None:
        """处理通知。只认 `notifications/initialized`。"""
        if method == "notifications/initialized":
            self._initialized = True

    def _dispatch(self, method, params):
        """分派一次请求。"""
        if method == "initialize":
            wanted = params.get("protocolVersion")
            version = wanted if wanted in PROTOCOL_VERSIONS else FALLBACK_PROTOCOL
            return {"protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": __version__},
                    "instructions": INSTRUCTIONS}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [dict(tool) for tool in TOOLS]}
        if method == "tools/call":
            return self._call_tool(params)
        raise _MethodError(METHOD_NOT_FOUND, f"不支持的方法：{method}")

    def _call_tool(self, params):
        """执行工具。

        工具执行中的一切失败都包成 `isError` 文本回给模型——包括连不上游戏这种
        最常见的失败。只有「没有这个工具」「arguments 不是对象」才算协议错误。
        """
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in self.session.tool_names():
            raise _MethodError(INVALID_PARAMS, f"没有这个工具：{name}")
        if not isinstance(arguments, dict):
            raise _MethodError(INVALID_PARAMS, "arguments 必须是对象")
        try:
            text = self.session.call_tool(name, arguments)
        except Exception as error:                     # 异常隔离：回文本，不倒服务
            return {"content": [{"type": "text",
                                 "text": f"{type(error).__name__}: {error}"}],
                    "isError": True}
        return {"content": [{"type": "text", "text": text}]}

    def _write(self, message) -> None:
        """写一行响应并立刻刷出。"""
        self.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.stdout.flush()


class _MethodError(Exception):
    """带 JSON-RPC 错误码的内部异常。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _error(identifier, code, message) -> dict:
    """构造一条 JSON-RPC 错误响应。"""
    return {"jsonrpc": "2.0", "id": identifier,
            "error": {"code": code, "message": message}}


def main(argv=None) -> int:
    """命令行入口：`python3 -m ra2agent.mcp`。"""
    import argparse
    parser = argparse.ArgumentParser(description="ra2agent 的 MCP 服务")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log", default=None, help="决策日志路径（JSONL）")
    parser.add_argument("--tick-interval", type=float, default=TICK_INTERVAL)
    args = parser.parse_args(argv)
    session = GameSession(args.host, args.port, args.log, args.tick_interval)
    try:
        McpServer(session).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
