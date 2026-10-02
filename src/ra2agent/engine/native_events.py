"""原版输入事件的只读解析；不发送命令，不提供执行确认。

字段来自 ra2yrproto 的 Event / MegaMission / TargetClass。服务端复用消息槽
可能残留旧 oneof，故只解析 event_type 对应的载荷。对象 m_ID 是原版编码，
不能解释为 pointer、array_index 或 Agent ID。
"""
from dataclasses import dataclass, field

from ..errors import ProtocolError
from .proto import fmap, signed64


def _integer(data, number, default=0):
    entries = data.get(number)
    if not entries:
        return default
    wire, value = entries[0]
    if wire != 0:
        raise ProtocolError(f"原版事件字段 {number} 不是整数")
    return value


def _message(data, number):
    entries = data.get(number)
    if not entries:
        return None
    wire, value = entries[0]
    if wire != 2:
        raise ProtocolError(f"原版事件字段 {number} 不是消息")
    return value


@dataclass(frozen=True)
class NativeTarget:
    """原版 TargetClass；空目标的 m_ID 也可能非零。"""

    m_id: int
    m_rtti: int

    @property
    def is_null(self) -> bool:
        return self.m_rtti == 0

    @property
    def cell(self) -> tuple[int, int] | None:
        """仅解码 RTTI=Cell 的地点，不保证其处于合法地图区域。"""
        if self.m_rtti != 11 or self.m_id < 0:
            return None
        return self.m_id % 1000, self.m_id // 1000

    @classmethod
    def parse(cls, blob):
        data = fmap(blob)
        return cls(signed64(_integer(data, 1)), signed64(_integer(data, 2)))


def _target(data, number):
    blob = _message(data, number)
    return None if blob is None else NativeTarget.parse(blob)


@dataclass(frozen=True)
class NativeMission:
    """MegaMission / MegaMission_F 的载荷；None 表示字段未提供。"""

    mission: int
    whom: NativeTarget | None
    target: NativeTarget | None
    destination: NativeTarget | None
    follow: NativeTarget | None = None
    is_planning_event: bool | None = None
    speed: int | None = None
    max_speed: int | None = None

    @classmethod
    def parse(cls, blob, event_type):
        if event_type not in (4, 5):
            raise ProtocolError(f"事件 {event_type} 不是 MegaMission")
        data = fmap(blob)
        common = dict(mission=signed64(_integer(data, 2)),
                      whom=_target(data, 1), target=_target(data, 3),
                      destination=_target(data, 4))
        if event_type == 4:
            return cls(**common, follow=_target(data, 5),
                       is_planning_event=bool(_integer(data, 6)))
        return cls(**common, speed=signed64(_integer(data, 5)),
                   max_speed=signed64(_integer(data, 6)))


@dataclass(frozen=True)
class NativeEvent:
    """一个列表槽的观测；重复观测和 out/do 转移不等于重复下令。

    is_executed 仅保留上游标志，不作为本次 Agent 请求的 applied 证明。
    Idle 仅解析 Target.whom；旧 DLL 未提供时为 None，其他载荷保留在 raw 中。
    """

    source: str
    event_type: int
    house_index: int
    frame: int
    timing: int
    is_executed: bool
    mega_mission: NativeMission | None
    raw: bytes = field(repr=False)
    idle_actor: NativeTarget | None = None

    @classmethod
    def parse(cls, blob, source):
        data = fmap(blob)
        event_type = _integer(data, 4)
        # Never inspect stale or unknown oneof fields for other event types.
        payload_number = {4: 8, 5: 9}.get(event_type)
        payload = (_message(data, payload_number)
                   if payload_number is not None else None)
        mission = (None if payload is None
                   else NativeMission.parse(payload, event_type))
        idle_payload = _message(data, 7) if event_type == 6 else None
        idle_actor = (None if idle_payload is None
                      else _target(fmap(idle_payload), 1))
        return cls(source=source, event_type=event_type,
                   house_index=signed64(_integer(data, 2)),
                   frame=_integer(data, 3), timing=_integer(data, 19),
                   is_executed=bool(_integer(data, 1)),
                   mega_mission=mission, raw=bytes(blob), idle_actor=idle_actor)


def parse_native_events(data) -> tuple[NativeEvent, ...]:
    """从已解码的 GameState 字段取三个列表，保留顺序与重复项。"""
    result = []
    for number, source in ((11, "out"), (12, "do"), (13, "megamission")):
        for wire, blob in data.get(number, ()):
            if wire != 2:
                raise ProtocolError(f"原版事件列表 {number} 不是消息")
            result.append(NativeEvent.parse(blob, source))
    return tuple(result)
