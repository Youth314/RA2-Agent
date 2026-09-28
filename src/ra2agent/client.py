"""与服务端通信的客户端。

一次连接对应一个结果队列，`queue_id` 即 WebSocket 的 socket id。命令分两类：
同步命令在工作线程内完成，结果立刻可取；排队命令要等游戏主循环执行闭包，见
`.agents/notes/命令接口源码结论.md#执行模型`。
"""
import time
from dataclasses import dataclass

from . import payloads
from .constants import (CMD_CLIENT, CMD_POLL_BLOCKING, DEFAULT_HOST,
                        DEFAULT_PORT, NS, PRODUCTION_STEPS, UnitAction)
from .errors import CommandFailed, ProtocolError, Timeout
from .proto import (any_unpack, fields, fmap, make_command, pb_bytes, pb_uint,
                    sub)
from .state import Coordinates, GameState, MapData, TypeTable
from .wire import WebSocket

#: 单次轮询的阻塞上限（毫秒）。服务端上限为 `POLL_BLOCKING_TIMEOUT`（2.5 秒）。
POLL_SLICE_MS = 500


@dataclass(frozen=True)
class CommandResult:
    """一条命令的执行结果。

    `code` 为 `None` 或 0 表示成功——proto3 不序列化默认值，故成功时该字段
    往往缺席。失败时 `payload` 是**请求的回声**而非结果，解析前必须先看
    `code`。
    """

    type: str
    payload: bytes
    code: int | None
    error: str
    command_id: int | None = None

    @property
    def ok(self) -> bool:
        """服务端是否报告成功。"""
        return self.code in (None, 0)

    def require_ok(self) -> "CommandResult":
        """失败时抛 `CommandFailed`。"""
        if not self.ok:
            raise CommandFailed(self.error or f"命令失败 code={self.code}",
                                command_type=self.type)
        return self


@dataclass(frozen=True)
class ServerConfig:
    """服务端配置，对应 `Configuration`。"""

    debug_log: bool
    record_filename: str
    traffic_filename: str
    parse_map_data_interval: int
    single_step: bool
    port: int
    max_connections: int
    allowed_hosts_regex: str
    log_filename: str


class Client:
    """ra2yrcpp 服务端的客户端。

    非线程安全；一个 `Client` 对应一条连接。
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT, timeout=10.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.ws: WebSocket | None = None
        self.queue_id: int | None = None

    # ------------------------------------------------------------ 连接
    def connect(self) -> int:
        """建立连接并完成握手，返回 `queue_id`。"""
        self.ws = WebSocket(self.host, self.port, timeout=self.timeout)
        body = self._request(CMD_CLIENT, NS + "GetSystemState")
        ack = _parse_ack(any_unpack(body)[1])
        if "queue_id" not in ack:
            raise ProtocolError("握手失败，未取得 queue_id")
        self.queue_id = ack["queue_id"]
        return self.queue_id

    def close(self) -> None:
        """关闭连接。"""
        if self.ws is not None:
            self.ws.close()
            self.ws = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()

    # ------------------------------------------------------------ 传输
    def _request(self, command_type, type_name, body=b"") -> bytes:
        """发送一帧命令并读取一帧响应，返回响应的 `body`。"""
        if self.ws is None:
            raise ProtocolError("尚未连接")
        self.ws.send_binary(make_command(command_type, type_name, body))
        raw = self.ws.recv()
        code, payload = None, b""
        for field, wire, value in fields(raw):
            if field == 1 and wire == 0:
                code = value
            elif field == 2 and wire == 2:
                payload = value
        if code not in (None, 0):
            raise ProtocolError(f"服务端错误 code={code}")
        return payload

    def send_async(self, type_name, body=b"") -> dict:
        """只发命令并读回回执，不等结果。

        测量生效延迟必须用它：等结果的写法会阻塞到主循环执行完闭包，测不出
        下令到生效之间经过了多少帧。
        """
        return _parse_ack(any_unpack(self._request(CMD_CLIENT, type_name, body))[1])

    def poll_all(self, poll_timeout_ms=2000) -> list[CommandResult]:
        """取回结果队列中当前可用的全部结果。

        不按 id 过滤，用于观察队列行为。队列容量为 32，溢出会覆盖最旧结果。
        """
        args = pb_uint(1, self.queue_id) + pb_uint(2, poll_timeout_ms)
        body = self._request(CMD_POLL_BLOCKING, NS + "PollResults",
                             pb_bytes(1, args))
        _, payload = any_unpack(body)
        out = []
        for field, wire, value in fields(payload):
            if field != 2 or wire != 2:
                continue
            for result_field, result_wire, blob in fields(value):
                if result_field == 1 and result_wire == 2:
                    out.append(_parse_command_result(blob))
        return out

    def send_command(self, type_name, body=b"", poll_timeout_ms=5000) -> CommandResult:
        """发送命令并取回其执行结果。"""
        ack = self.send_async(type_name, body)
        if "id" not in ack:
            raise ProtocolError(f"未取得命令 id（{type_name}）")
        return self._poll_for(ack["id"], poll_timeout_ms)

    def _poll_for(self, command_id, poll_timeout_ms) -> CommandResult:
        """轮询直到取回指定 id 的结果；结果可能分多批到达。"""
        deadline = time.monotonic() + poll_timeout_ms / 1000.0
        while time.monotonic() < deadline:
            try:
                for result in self.poll_all(POLL_SLICE_MS):
                    if result.command_id == command_id:
                        return result
            except (OSError, ProtocolError):
                continue
        return CommandResult(type="POLL_TIMEOUT", payload=b"", code=None,
                             error="poll timeout")

    # ------------------------------------------------------------ 观测
    def get_state(self, poll_timeout_ms=5000) -> GameState:
        """读取一帧游戏状态。"""
        result = self.send_command(NS + "GetGameState", b"", poll_timeout_ms)
        if result.type == "POLL_TIMEOUT":
            raise Timeout("GetGameState 超时；游戏是否失焦暂停？")
        result.require_ok()
        return GameState.parse(sub(result.payload, 1))

    def read_map(self, poll_timeout_ms=20000) -> MapData:
        """取完整地图。

        地图只在 `StorageValue` 中，`GameState.map_data` 从不填充，故须单独取
        一次；之后按 `GameState.cells_difference` 增量更新。
        """
        result = self.send_command(
            NS + "ReadValue", payloads.read_value(payloads.STORAGE_MAP_DATA_SOA),
            poll_timeout_ms)
        if result.type == "POLL_TIMEOUT":
            raise Timeout("ReadValue(map_data_soa) 超时")
        result.require_ok()
        return MapData.parse(result.payload)

    def read_object_types(self, poll_timeout_ms=20000) -> TypeTable:
        """取对象类型表。类型表只在首帧下发，故从 `initial_game_state` 取。"""
        result = self.send_command(
            NS + "ReadValue",
            payloads.read_value(payloads.STORAGE_INITIAL_GAME_STATE),
            poll_timeout_ms)
        if result.type == "POLL_TIMEOUT":
            raise Timeout("ReadValue(initial_game_state) 超时")
        result.require_ok()
        return TypeTable.parse(result.payload)

    def frame(self) -> int:
        """当前游戏帧号。"""
        return self.get_state().frame

    def is_advancing(self, window=1.5, min_frames=1) -> bool:
        """游戏主循环是否在推进。

        RA2 单机在窗口失焦时暂停主循环，排队命令不会执行。执行器据此判断是否
        值得继续等待，而不是把超时当作命令失败。
        """
        before = self.frame()
        time.sleep(window)
        return self.frame() - before >= min_frames

    # ------------------------------------------------------------ 配置
    def inspect_config(self, poll_timeout_ms=5000) -> ServerConfig:
        """读取服务端配置。"""
        result = self.send_command(NS + "InspectConfiguration", b"",
                                   poll_timeout_ms)
        result.require_ok()
        return _parse_config(sub(result.payload, 1))

    def update_config(self, parse_map_data_interval=None, single_step=None,
                      poll_timeout_ms=5000) -> ServerConfig:
        """改写服务端配置。

        只有 `parse_map_data_interval` 与 `single_step` 会被应用，其余字段不
        生效；`parse_map_data_interval` 为 0 会被强制改回 1。
        """
        body = payloads.inspect_configuration(
            update=True, parse_map_data_interval=parse_map_data_interval,
            single_step=single_step)
        result = self.send_command(NS + "InspectConfiguration", body,
                                   poll_timeout_ms)
        result.require_ok()
        return _parse_config(sub(result.payload, 1))

    # ------------------------------------------------------------ 指令
    def unit_order(self, units, action: UnitAction, target_object=None,
                   coordinates: Coordinates | None = None,
                   poll_timeout_ms=5000) -> CommandResult:
        """下发 `UnitOrder`。"""
        return self.send_command(
            NS + "UnitOrder",
            payloads.unit_order(units, action, target_object, coordinates),
            poll_timeout_ms)

    def click_event(self, units, event, poll_timeout_ms=5000) -> CommandResult:
        """下发 `ClickEvent`。"""
        return self.send_command(NS + "ClickEvent",
                                 payloads.click_event(units, event),
                                 poll_timeout_ms)

    def produce_order(self, entry, poll_timeout_ms=10000) -> CommandResult:
        """开始生产。`entry` 为 `ObjectType`。"""
        return self.send_command(NS + "ProduceOrder",
                                 payloads.produce_order(entry), poll_timeout_ms)

    def place_query(self, entry, house, candidates,
                    poll_timeout_ms=20000) -> list[Coordinates]:
        """查询候选坐标中合法的放置位置，返回其子集。"""
        body = payloads.place_query(entry, house, candidates)
        result = self.send_command(NS + "PlaceQuery", body, poll_timeout_ms)
        result.require_ok()
        return [Coordinates.parse(v) for _, v in fmap(result.payload).get(3, [])]

    def place_building(self, building, coordinates,
                       poll_timeout_ms=15000) -> CommandResult:
        """放置已完工的建筑。"""
        return self.send_command(
            NS + "PlaceBuilding",
            payloads.place_building(building, coordinates), poll_timeout_ms)

    def add_event(self, event_type, poll_timeout_ms=10000, **kwargs) -> CommandResult:
        """注入引擎事件。"""
        return self.send_command(NS + "AddEvent",
                                 payloads.add_event(event_type, **kwargs),
                                 poll_timeout_ms)

    def add_message(self, text, duration_frames=150, color=0,
                    poll_timeout_ms=5000) -> CommandResult:
        """在游戏内显示一行文本。"""
        return self.send_command(
            NS + "AddMessage",
            payloads.add_message(text, duration_frames, color), poll_timeout_ms)

    def wait_production(self, owner=None, timeout_s=60.0,
                        poll_interval=0.15):
        """等待己方某一生产队列完工，返回其 `Factory`；超时返回 `None`。"""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.get_state()
            factories = state.own_factories()
            if owner is not None:
                factories = [f for f in factories if f.owner == owner]
            done = [f for f in factories
                    if f.completed or f.progress_timer >= PRODUCTION_STEPS]
            if done:
                return done[0]
            time.sleep(poll_interval)
        return None


# ---------------------------------------------------------------- 解析辅助
def _parse_ack(payload) -> dict:
    """解析 `RunCommandAck{id, queue_id}`。"""
    ack = {}
    for field, wire, value in fields(payload):
        if field == 1 and wire == 0:
            ack["id"] = value
        elif field == 2 and wire == 0:
            ack["queue_id"] = value
    return ack


def _parse_command_result(blob) -> CommandResult:
    """解析 `CommandResult{command_id, result, result_code, error_message}`。"""
    command_id, result_code, error = None, None, ""
    body = b""
    for field, wire, value in fields(blob):
        if field == 1 and wire == 0:
            command_id = value
        elif field == 2 and wire == 2:
            body = value
        elif field == 3 and wire == 0:
            result_code = value
        elif field == 4 and wire == 2:
            error = value.decode(errors="replace")
    type_name, payload = any_unpack(body)
    return CommandResult(type=type_name, payload=payload, code=result_code,
                         error=error, command_id=command_id)


def _parse_config(blob) -> ServerConfig:
    """解析 `Configuration`。"""
    present = fmap(blob)
    get = lambda f, d=0: present.get(f, [(0, d)])[0][1]  # noqa: E731

    def text(field):
        value = get(field, b"")
        return value.decode(errors="replace") if isinstance(value, bytes) else str(value)

    return ServerConfig(
        debug_log=bool(get(1)),
        record_filename=text(2),
        traffic_filename=text(3),
        parse_map_data_interval=get(4),
        single_step=bool(get(5)),
        port=get(6),
        max_connections=get(7),
        allowed_hosts_regex=text(8),
        log_filename=text(9),
    )
