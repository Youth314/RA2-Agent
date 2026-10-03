"""MCP 服务：把指挥层的工具暴露给 DSH。

JSON-RPC 2.0，stdio 传输，一行一条消息；只用标准库（本项目不装第三方包）。

**启动时不连接游戏。** DSH 会先用一个临时探针进程列工具，那时游戏可能没开；
真正的连接在第一次调用局内工具时建立，随后由后台线程按约 2 Hz 推进技法层。
`game` 工具管的是游戏进程本身，故它不走这条连接。

stdout 只放协议消息，日志一律走 stderr，否则会污染流。
"""
import dataclasses
import json
import sys
import threading
import time

from . import __version__
from .engine.client import Client
from .engine.identity import IdentityTable
from .command import CallRequest, Commander
from .data.catalogue import Catalogue
from .constants import DEFAULT_HOST, DEFAULT_PORT, LoadStage
from .errors import ConnectionLost, ProtocolError, Ra2Error
from .runtime.executor import Executor
from .deploy.game import GameHost, LOOP_STALL_SECONDS
from .runtime.intents import DecisionLog
from .deploy.match import MatchRoster
from .runtime.micro import MicroLayer
from .engine.observation import Observer
from .data.rules import attach_type_aliases
from .wake import WakeBridge, WakePolicy
from .tactics import TacticPolicy, TacticRegistry
from .engine.validate import Validator

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
    "红警 2 对局工具。局内四个：status 读局势（每次醒来先看它，新结果与告警只报一次）、"
    "tactics 读当前可用的技法卡片、call 下达任务（立刻返回受理结果，生效与否之后用 "
    "status 看）、cancel 撤销在管任务。局外一个：game 管游戏进程本身（status 看进程与"
    "焦点、start 启动、stop 停止、focus 抢回焦点），游戏没开时也用它。"
    "一局按这样走：status 看局面，tactics 挑技法，call 下达，隔几拍再 status 跟进。"
    "开局前先读 skill ra2-play——单位、造价、克制与玩家的黑话都在它指向的 codex/ 里。"
    "任何对局动作都必须经过技法，没有直接向引擎下命令的工具；"
    "单位一律用 status 里给出的 id。"
    "连接重建后旧 ID 与任务失效，必须重新读 status；已提交的原生命令可能继续，勿盲重发。"
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
    {
        "name": "game",
        "description": "管游戏进程本身，与对局无关，故游戏没在跑时也能用。"
                       "action=status 看进程、端口、崩溃留证与窗口焦点；"
                       "action=start 启动游戏（立刻返回，进展用 status 看）；"
                       "action=stop 停止游戏，对局进行中要加 force=true；"
                       "action=focus 抢回焦点（窗口失焦会让主循环暂停）。"
                       "用户没说要玩时不要自己 start。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["status", "start", "stop", "focus"],
                           "description": "要做的动作"},
                "force": {"type": "boolean",
                          "description": "stop 专用：对局进行中必须显式给 true"},
            },
            "required": ["action"],
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

DEFAULT_ALIASES_PATH = "corpus/derived/rules.json"
#: 唤醒桥的配置。不存在就用默认值。
DEFAULT_WAKE_CONFIG = "config/wake.json"
#: 对局名册。`--player` 用它取该玩家的游戏目录与探针端口。
DEFAULT_ROSTER = "config/match.json"


class GameSession:
    """与游戏的一条会话：懒连接，一个后台线程推进技法层。

    连接由本进程独占；`Client` 非线程安全，故所有访问都在同一把锁下。
    """

    def __init__(self, host=None, port=None, log_path=None,
                 tick_interval=TICK_INTERVAL, on_log=None, game_host=None,
                 aliases_path=None, wake_config_path=None, wake_session=None):
        self.host = host
        self.port = port
        self.log_path = log_path
        self.aliases_path = aliases_path or DEFAULT_ALIASES_PATH
        self.wake_config_path = wake_config_path or DEFAULT_WAKE_CONFIG
        #: 唤醒投给哪个 DSH 会话。留空则由桥插件按唯一候选去猜——同机两个玩家时
        #: 会唤醒错人，故每个玩家的服务进程都该给一个。
        self.wake_session = wake_session or ""
        self.tick_interval = tick_interval
        self.on_log = on_log
        self.game_host = game_host or GameHost(host=host or DEFAULT_HOST,
                                               port=port or DEFAULT_PORT)
        self._lock = threading.RLock()
        self._client = None
        self._observer = None
        self._layer = None
        self._commander = None
        self._log = None
        self._observation = None
        #: 上一次 `game status` 看到的帧与时刻，用来判主循环到底有没有在跑。
        self._frame_sample = None
        self._stop = threading.Event()
        self._thread = None
        self._last_error = ""
        self._broken = False
        self._match_player = None
        self._last_polled_frame = None
        # 只在同一个 MCP 进程内延续分配起点；不保留旧对象或旧任务。
        self._next_agent_id = 1
        self._context_generation = 0
        self._status_generation = None

    # ------------------------------------------------------------ 生命周期
    def ensure(self):
        """确保已连接并已启动推进线程；连接坏了就整条重建。

        连接失败时抛的是一句人话，而不是 `ConnectionRefusedError`——模型据此
        才知道该去调 `game`。
        """
        with self._lock:
            if self._client is not None and not self._broken:
                return self
            stale = self._client is not None or self._thread is not None
        if stale:
            self.reset()
        with self._lock:
            if self._client is not None:
                return self
            try:
                self._connect()
            except ProtocolError as error:
                if isinstance(error, ConnectionLost):
                    raise Ra2Error(f"游戏连接断了：{error}。用 game status 看进程。") from error
                raise Ra2Error(f"当前无法建立局内会话：{error}。"
                               "进入活动对局后重试 status。") from error
            except (Ra2Error, OSError) as error:
                raise Ra2Error(f"游戏没在跑：{error}。用 game status 看进程，"
                               f"game start 启动。") from error
            return self

    def _build_wake(self, log):
        """按 `config/wake.json` 建唤醒桥。文件不在就用默认值。"""
        try:
            policy = WakePolicy.load(self.wake_config_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self._emit(f"唤醒配置读不了，改用默认值：{error}")
            policy = WakePolicy()
        if self.wake_session:
            policy = dataclasses.replace(policy, session=self.wake_session)
        return WakeBridge(endpoint=policy.endpoint, policy=policy, log=log,
                          timeout=policy.timeout)

    def reset(self):
        """丢掉整条会话，下次调用重建。

        游戏停过再起，帧号归零、地图与单位指针全变，旧的观测器一律不能留。
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        with self._lock:
            self._remember_identity()
            if self._client is not None:
                self._client.close()
            if self._log is not None:
                self._log.close()
            self._client = self._observer = self._layer = None
            self._commander = None
            self._log = None
            self._observation = None
            self._broken = False
            self._last_error = ""
            self._match_player = None
            self._last_polled_frame = None
            self._frame_sample = None
            self._status_generation = None

    def _remember_identity(self):
        """丢弃 Observer 前保存已消耗的 ID 范围。调用者持有会话锁。"""
        if self._observer is not None:
            self._next_agent_id = max(self._next_agent_id,
                                      self._observer.identity.next_id)

    def _connect(self):
        """连游戏、取底图与类型表、建技法层，并起后台线程。"""
        client = Client(self.host or DEFAULT_HOST, self.port or DEFAULT_PORT)
        client.connect()
        observer = Observer(client, identity=IdentityTable(
            start_id=self._next_agent_id)).bootstrap()
        # 技法与文档按注册名说话，而引擎只给显示名，故补一份别名
        aliases = attach_type_aliases(observer.types, self.aliases_path)
        if aliases == 0:
            self._emit(f"没读到 {self.aliases_path}，技法里只能用显示名指代类型")
        # 可造目录：与别名同一份文件。缺它只是少一段「可造」与前提条件，
        # 不影响对局，故不报错。
        observer.catalogue = Catalogue.load(self.aliases_path)
        registry = TacticRegistry(TacticPolicy.load("config/tactics.json")).load_builtin()
        try:
            observation = observer.poll()
            player = self._active_player(observation)
        except Ra2Error:
            client.close()
            raise
        log = DecisionLog(self.log_path) if self.log_path else None
        executor = Executor(client, observer.identity, types=observer.types,
                            validator=Validator(observer.map_data), log=log,
                            read_state=lambda: observer.poll().state)
        layer = MicroLayer(observer, registry, executor, log=log,
                           wake=self._build_wake(log))
        self._client, self._observer, self._layer = client, observer, layer
        self._commander = Commander(layer, observer, log=log)
        # 自动触发挂在技法层的每拍开头：本拍发起的任务同拍就能下令
        layer.on_tick = self._commander.auto
        self._log = log
        self._observation = observation
        self._match_player = player
        self._last_polled_frame = self._observation.frame
        self._context_generation += 1
        self._status_generation = None
        self._emit("已连接游戏：帧 %d，地图 %dx%d，技法 %d 条，库指纹 %s"
                   % (self._observation.frame, observer.map_data.width,
                      observer.map_data.height, len(registry), registry.fingerprint()))
        self._stop.clear()
        self._thread = threading.Thread(target=self._tick_forever,
                                        name="ra2-tick", daemon=True)
        self._thread.start()

    def _tick_forever(self):
        """后台轮询：活动对局的帧号推进后才执行技法。

        连接断了就标记并退出，让下次工具调用整条重建；失焦或单条命令失败只记
        事件，不影响后续 tick。
        """
        while not self._stop.wait(self.tick_interval):
            with self._lock:
                if self._layer is None:
                    return
                try:
                    if not self._advance():
                        return
                except ConnectionLost as error:
                    self._broken = True
                    self._fail(f"连接断了：{error}")
                    return
                except Ra2Error as error:
                    self._fail(str(error))
                except OSError as error:
                    self._broken = True
                    self._fail(f"连接出错：{error}")
                    return

    @staticmethod
    def _active_player(observation):
        """返回活动席位身份；不猜测缺失或不唯一的 current_player。"""
        state = observation.state
        if state is None or state.stage != LoadStage.INGAME:
            raise ProtocolError("当前不是活动对局")
        house = state.player_house()
        if house is None or any(getattr(house, flag, False) for flag in (
                "defeated", "is_winner", "is_loser", "is_game_over")):
            raise ProtocolError("当前玩家已结束对局")
        return house.pointer, house.array_index

    def _discard_match(self, reason):
        """边界变化后停止旧任务；连接由下一次 ensure/reset 关闭重建。"""
        self._broken = True
        self._remember_identity()
        self._layer = self._commander = self._observer = None
        self._observation = None
        self._match_player = self._last_polled_frame = None
        self._fail(f"{reason}；旧任务已丢弃，下次调用重建会话")
        return False

    def _advance(self):
        """在会话锁下轮询一拍。False 表示已跨局次边界，线程应退出。"""
        try:
            observation = self._observer.poll()
            player = self._active_player(observation)
        except ConnectionLost:
            raise
        except ProtocolError as error:
            return self._discard_match(str(error))
        if self._match_player is not None and player != self._match_player:
            return self._discard_match("current_player 阵营已变化")
        previous = self._last_polled_frame
        if previous is not None and observation.frame < previous:
            return self._discard_match("游戏帧号回退")
        self._observation = observation
        self._match_player = player
        self._last_polled_frame = observation.frame
        # 第一份采样只建立基线；暂停时既不自动触发，也不向引擎排队。
        if previous is None or observation.frame == previous:
            return True
        self._layer.tick(observation)
        # 执行器等待回执也会更新 Observer；保留其最新观测与帧基线。
        observation = self._observer.observe()
        try:
            player = self._active_player(observation)
        except ProtocolError as error:
            return self._discard_match(str(error))
        if player != self._match_player or observation.frame < self._last_polled_frame:
            return self._discard_match("执行期间局次边界已变化")
        self._observation = observation
        self._last_polled_frame = observation.frame
        return True

    def close(self):
        """停线程、关连接。"""
        self.reset()

    # ------------------------------------------------------------ 工具
    def call_tool(self, name, arguments) -> str:
        """执行一个工具，返回给模型的文本。出错抛 `Ra2Error` 或 `ValueError`。

        `game` 不 `ensure()`：它管的就是游戏还没在跑的情形。
        """
        if name == "game":
            return self._game(arguments)
        if name not in ("status", "tactics", "call", "cancel"):
            raise ValueError(f"没有这个工具：{name}")
        self.ensure()
        with self._lock:
            if self._broken or self._commander is None:
                raise Ra2Error("会话已失效，请重新调用 status；不要重发旧任务。")
            if name == "status":
                text = self._commander.status(self._observation).render()
                stamp = self._context_stamp()
                self._status_generation = self._context_generation
                return stamp + "\n" + text
            if name == "tactics":
                with self._lock:
                    observation = self._observation
                cards = self._commander.tactics(arguments.get("query"), observation)
                if not cards:
                    return self._context_stamp() + "\n此刻没有可用技法"
                # 带上帧号：卡片是按**那一刻**的局面筛的，不带帧号就没法回答
                # 「为什么上一拍看不见、这一拍又出现了」这类对不上的争论。
                stamp = "" if observation is None else f"帧 {observation.frame}｜"
                return self._context_stamp() + "\n" + stamp + "\n".join(card.text() for card in cards)
            if name in ("call", "cancel") and self._status_generation != self._context_generation:
                raise Ra2Error(self._context_stamp() + "\n先调用 status 读取当前对象与任务，"
                               "再使用本次 ID 下令；本次请求未受理。")
            if name == "call":
                return self._call(arguments)
            if name == "cancel":
                return Commander.render_cancels(
                    self._commander.cancel(arguments["intent_ids"]))
        raise ValueError(f"没有这个工具：{name}")

    def _context_stamp(self):
        stamp = f"会话上下文 {self._context_generation}"
        if self._status_generation == self._context_generation:
            return stamp
        if self._context_generation <= 1:
            return stamp + "：首次连接，请使用本次 status 的 ID。"
        return (stamp + "：会话已重建，旧 ID 与任务失效；已提交的原生命令未撤销，"
                "结果可能未知，勿盲重发。")

    # ------------------------------------------------------------ 门外
    def _game(self, arguments) -> str:
        """游戏进程本身：起停、巡检、焦点。不依赖对局连接。"""
        action = arguments.get("action")
        if action == "status":
            return self._game_status()
        if action == "start":
            return self._game_start()
        if action == "stop":
            return self._game_stop(bool(arguments.get("force")))
        if action == "focus":
            return self._game_focus()
        raise ValueError(f"没有这个 action：{action!r}"
                         f"（可用 status / start / stop / focus）")

    def _game_status(self) -> str:
        """宿主侧巡检；已经连着的话再报一行对局。"""
        state = self.game_host.inspect()
        lines = list(self.game_host.describe(state))
        with self._lock:
            observation = self._observation if not self._broken else None
        if observation is not None and observation.state is not None:
            lines.append(f"对局：帧 {observation.frame}，stage={observation.state.stage}，"
                         f"阵营 {observation.house.name}")
            lines.append(self._loop_line(observation.frame))
        elif state.listening:
            lines.append("对局：端口通但还没连上——调一次 status 就会连。")
        return "\n".join(lines)

    def _loop_line(self, frame) -> str:
        """主循环有没有在跑：**按帧号推进判，不按前台窗口标题**。

        窗口在不在前台与主循环跑不跑是两件事。同桌面开着两个同名实例时，按前台
        标题判必然对至少一方为假——实测两个测试 agent 都收到过「窗口失焦，主循环
        暂停」，而同期帧号一直在涨，差点让他们去抢焦点（抢到对手那个等于替对方
        按暂停）。
        """
        now = time.monotonic()
        last, self._frame_sample = self._frame_sample, (frame, now)
        if last is None:
            return "主循环：首次采样，再读一次就能判"
        previous, at = last
        elapsed = max(0.0, now - at)
        if frame > previous:
            return f"主循环：在跑（帧 {previous}→{frame}，{elapsed:.1f} 秒）"
        if elapsed < LOOP_STALL_SECONDS:
            return (f"主循环：帧没变（{elapsed:.1f} 秒，不到 "
                    f"{LOOP_STALL_SECONDS:.0f} 秒的判定阈值）")
        return (f"主循环：疑似暂停——帧 {frame} 已 {elapsed:.1f} 秒没动，"
                f"用 game focus 抢回焦点")

    def _game_start(self) -> str:
        """起游戏。已经在跑就不重复起；起之前先丢掉可能陈旧的会话。"""
        processes = self.game_host.processes()
        if processes:
            pids = "、".join(str(process.pid) for process in processes)
            return f"游戏已经在跑（PID {pids}），没有重复启动。用 game status 看进展。"
        self.reset()
        self.game_host.launch()
        return ("已发起启动。约 3 秒后服务在听，进对局要更久；用 game status 看进展，"
                "进对局之后第一次读局势会自动连上。")

    def _game_stop(self, force) -> str:
        """停游戏。对局进行中要显式 `force`——那会丢掉这一局。"""
        processes = self.game_host.processes()
        if not processes:
            self.reset()
            return "游戏没在跑，无需停止。"
        if self._in_match() and not force:
            return ("对局进行中，停止会丢掉这一局。真要停请给 force=true。")
        pids = self.game_host.terminate()
        self.reset()
        killed = "、".join(str(pid) for pid in pids)
        return f"已停止游戏（PID {killed}），会话已丢弃，下次调用重建。"

    def _game_focus(self) -> str:
        """抢回焦点。

        失焦**可能**让主循环暂停，但两件事得分开说：先看帧号有没有在涨（`game
        status` 会报），再决定要不要抢。同桌面两个同名实例时按标题找窗口本身就有
        歧义，故这里把「找到几个、置前成没成」一起报出来，不给一句含糊的「没找到？」。
        """
        if not self.game_host.processes():
            return "游戏没在跑，无法抢焦点。用 game start 启动。"
        windows = list(self.game_host.window_probe())
        if self.game_host.focus_game():
            route = getattr(self.game_host, "last_focus_route", "")
            note = f"（{route}）" if route else ""
            if len(windows) > 1 and "按标题" in route:
                note += "——同名实例分辨不出是哪一份，请用 game status 的帧号确认"
            return f"已把游戏窗口置前{note}。"
        if not windows:
            return "没能置前——没找到标题含游戏名的窗口。"
        return (f"没能置前（找到 {len(windows)} 个同名窗口，置前失败）——"
                f"可能是 Windows 的前台限制；先看 game status 的帧号还在不在涨，"
                f"别反复重试。")

    def _in_match(self):
        """当前是否已进对局。没连上或还在载入都算没进。"""
        with self._lock:
            observation = self._observation if not self._broken else None
        if observation is None or observation.state is None:
            return False
        return (observation.state.stage == LoadStage.INGAME
                and observation.state.player_house() is not None)

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

        工具执行中的一切失败都包成 `isError` 文本回给模型——包括游戏没在跑这种
        最常见的失败。只有「没有这个工具」「arguments 不是对象」才算协议错误。

        `Ra2Error` 与 `ValueError` 的文本是本项目自己写的人话，原样给出；其它
        异常带上类型名，便于区分「没料到的炸了」。
        """
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in self.session.tool_names():
            raise _MethodError(INVALID_PARAMS, f"没有这个工具：{name}")
        if not isinstance(arguments, dict):
            raise _MethodError(INVALID_PARAMS, "arguments 必须是对象")
        try:
            text = self.session.call_tool(name, arguments)
        except (Ra2Error, ValueError) as error:        # 异常隔离：回文本，不倒服务
            return _tool_error(str(error))
        except Exception as error:                     # 兜底：连没料到的也不倒服务
            return _tool_error(f"{type(error).__name__}: {error}")
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


def _tool_error(text) -> dict:
    """构造一条工具失败结果：模型看到的是人话，不是异常类型。"""
    return {"content": [{"type": "text", "text": text}], "isError": True}


def resolve_player(player, roster_path, host=None, port=None):
    """按名册给一个玩家配出探针端口与宿主。

    一台机器上跑一局时，每个玩家有**自己的**游戏目录与探针端口，两者都来自名册
    而不是模块常量，所以同一个服务进程只能服务名册里的一方。

    @param player: 名册里的玩家名。
    @param roster_path: 名册路径。
    @param host: 探针地址；默认 `127.0.0.1`。
    @param port: 探针端口；默认取名册里该玩家的那个。
    @returns: `(port, game_host)`。
    @raises KeyError: 名册里没有这个玩家。
    @raises FileNotFoundError: 名册文件不存在。
    @raises ValueError: 名册本身不自洽。
    """
    participant = MatchRoster.load(roster_path).get(player)
    resolved_port = participant.probe_port if port is None else port
    game_host = GameHost(host=host or DEFAULT_HOST, port=resolved_port,
                         game_dir=participant.game_dir,
                         game_dir_wsl=participant.wsl_dir,
                         crash_report=participant.wsl_dir + "/EXCEPT_CNCNET.TXT")
    return resolved_port, game_host


def main(argv=None) -> int:
    """命令行入口：`python3 -m ra2agent.mcp`。

    一台机器上跑一局时，每个玩家有**自己的**服务进程：用 `--player` 从名册取出
    它那份游戏目录与探针端口，用 `--wake-session` 指明唤醒投给哪个 DSH 会话。
    两者都不给就是原来的单实例用法。
    """
    import argparse

    parser = argparse.ArgumentParser(description="ra2agent 的 MCP 服务")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--log", default=None, help="决策日志路径（JSONL）")
    parser.add_argument("--tick-interval", type=float, default=TICK_INTERVAL)
    parser.add_argument("--roster", default=DEFAULT_ROSTER,
                        help="对局名册路径，默认 config/match.json")
    parser.add_argument("--player", default=None,
                        help="名册里的玩家名；给了就用它那份目录与探针端口")
    parser.add_argument("--wake-session", default=None,
                        help="唤醒投给哪个 DSH 会话；不给则由桥插件按唯一候选去猜")
    args = parser.parse_args(argv)

    game_host = None
    if args.player:
        args.port, game_host = resolve_player(args.player, args.roster,
                                              host=args.host, port=args.port)

    session = GameSession(args.host, args.port, args.log, args.tick_interval,
                          game_host=game_host, wake_session=args.wake_session)
    try:
        McpServer(session).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
