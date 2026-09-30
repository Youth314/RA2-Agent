"""意图 schema。

设计见 `.agents/notes/架构设计.md#意图-schema`。要点：

- 意图是**持久目标**而非一次性命令，有生命周期与 TTL。
- 各层交换意图，只有 L0 把意图翻译成引擎命令。
- 意图必须可序列化，且带来源与 TTL，使接管与过期可自动处理。
- 意图引用对象用 Agent 侧稳定 id，不用引擎指针——指针在单位变身时会变。

载荷用类型化子类加注册表，而非自由字典，以保留类型约束。
"""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import IntEnum, StrEnum
from typing import Any

from .errors import Ra2Error

#: TTL 用游戏帧计时。该常量仅在需要把人类口述的秒数换算成帧时使用，
#: 取值来自测绘：44 fps 左右。
NOMINAL_FPS = 44


class Layer(IntEnum):
    """决策层。数值越小越接近引擎。"""

    L0_INFRASTRUCTURE = 0
    L1_TACTIC = 1
    L2_COMMAND = 2

    @property
    def label(self) -> str:
        """人类可读的层名。"""
        return {
            Layer.L0_INFRASTRUCTURE: "基础设施",
            Layer.L1_TACTIC: "技法",
            Layer.L2_COMMAND: "指挥",
        }[self]


class IntentState(StrEnum):
    """意图的生命周期状态。"""

    ACTIVE = "active"
    SATISFIED = "satisfied"
    #: 技法明说此刻无事可做（不是出错）：单位交还，状态不动。
    IDLE = "idle"
    FAILED = "failed"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


#: 终态，不再接受更新。
TERMINAL_STATES = frozenset({
    IntentState.SATISFIED, IntentState.IDLE, IntentState.FAILED,
    IntentState.EXPIRED, IntentState.SUPERSEDED,
})


class Stance(StrEnum):
    """接战姿态，影响 L1 把移动意图展开成哪一种引擎动作。"""

    AGGRESSIVE = "aggressive"   # 移动并迎击，对应 ATTACK_MOVE
    PASSIVE = "passive"         # 只移动，不主动交战，对应 MOVE
    HOLD = "hold"               # 原地不动，对应 STOP


class Scope:
    """意图涉及的对象或区域，所有权判定的依据。

    二者至少有其一：只涉及对象时 `region` 为空，只涉及区域时 `objects` 为空。
    二者可以同时给出，表示「这些对象在该区域内」。
    """

    __slots__ = ("objects", "region")

    def __init__(self, objects=(), region=None):
        self.objects = tuple(objects)
        self.region = tuple(region) if region is not None else None
        if not self.objects and self.region is None:
            raise ValueError("Scope 至少需要 objects 或 region 之一；"
                             "确实不涉及对象时用 Scope.empty()")

    @classmethod
    def empty(cls) -> "Scope":
        """不涉及任何对象的意图，例如阵营级的生产。

        这类意图的归属依据是玩家本身，故显式声明为空，而不是随手给一个假对象。
        """
        scope = cls.__new__(cls)
        scope.objects = ()
        scope.region = None
        return scope

    @property
    def is_empty(self) -> bool:
        """是否不涉及任何对象与区域。"""
        return not self.objects and self.region is None

    def to_dict(self) -> dict:
        """序列化为可 JSON 编码的字典。"""
        return {"objects": list(self.objects),
                "region": list(self.region) if self.region else None}

    @classmethod
    def from_dict(cls, data) -> "Scope":
        """从字典还原。两项皆空时还原为 `Scope.empty()`，不报错。"""
        objects = data.get("objects") or ()
        region = data.get("region")
        if not objects and region is None:
            return cls.empty()
        return cls(objects=objects, region=region)

    def __eq__(self, other):
        return (isinstance(other, Scope) and self.objects == other.objects
                and self.region == other.region)

    def __repr__(self):
        return f"Scope(objects={self.objects!r}, region={self.region!r})"


@dataclass
class Intent:
    """所有意图的共有信封。

    子类补充载荷字段。`kind` 由 `@register` 决定，不要求调用方填写。
    """

    #: 由注册表填入，子类不应手工设置。
    kind: str = field(default="", init=False)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    layer: Layer = Layer.L1_TACTIC
    issuer: str = "agent"
    scope: Scope = field(default_factory=lambda: Scope(objects=(0,)))
    created_frame: int = 0
    ttl_frames: int | None = None
    parent: str | None = None
    state: str = IntentState.ACTIVE

    # ------------------------------------------------------------ 生命周期
    def expires_at(self) -> int | None:
        """到期的游戏帧；无 TTL 时返回 `None`。"""
        if self.ttl_frames is None:
            return None
        return self.created_frame + self.ttl_frames

    def is_expired(self, frame: int) -> bool:
        """按给定帧号判断是否已过期。"""
        limit = self.expires_at()
        return limit is not None and frame >= limit

    def is_terminal(self) -> bool:
        """是否已进入终态。"""
        return self.state in TERMINAL_STATES

    # ------------------------------------------------------------ 序列化
    def to_dict(self) -> dict:
        """序列化为可 JSON 编码的字典。"""
        out: dict[str, Any] = {}
        for info in fields(self):
            value = getattr(self, info.name)
            out[info.name] = value.to_dict() if isinstance(value, Scope) else value
        out["layer"] = int(self.layer)
        return out

    @classmethod
    def from_dict(cls, data: dict) -> "Intent":
        """按 `kind` 从字典还原为具体子类。"""
        kind = data.get("kind")
        target = _REGISTRY.get(kind)
        if target is None:
            raise Ra2Error(f"未知的意图类型 {kind!r}")
        payload = dict(data)
        payload["layer"] = Layer(payload.get("layer", Layer.L1_TACTIC))
        if "scope" in payload:
            payload["scope"] = Scope.from_dict(payload["scope"])
        # 按具体子类中可经构造函数传入的字段过滤；kind 为 init=False，故被排除
        known = {info.name for info in fields(target) if info.init}
        extra = {k: v for k, v in payload.items() if k in known}
        return target(**extra)

    def child(self, intent: "Intent") -> "Intent":
        """把另一条意图登记为本意图的子意图。"""
        intent.parent = self.id
        return intent


#: `kind` 到具体类的注册表。
_REGISTRY: dict[str, type] = {}


def register(kind):
    """把意图类登记到注册表，供反序列化时按 `kind` 查找。"""
    def decorate(cls):
        cls.kind = kind
        _REGISTRY[kind] = cls
        return cls
    return decorate


def registered_kinds() -> list[str]:
    """已注册的全部意图类型。"""
    return sorted(_REGISTRY)


# ---------------------------------------------------------------- 具体意图
@register("move_to")
@dataclass
class MoveTo(Intent):
    """把若干单位移动到指定格。"""

    units: tuple[int, ...] = ()
    cell: tuple[int, int] = (0, 0)
    stance: str = Stance.AGGRESSIVE


@register("attack")
@dataclass
class Attack(Intent):
    """攻击指定目标对象。"""

    units: tuple[int, ...] = ()
    target: int = 0


@register("hold")
@dataclass
class Hold(Intent):
    """停止并原地驻守。"""

    units: tuple[int, ...] = ()


@register("deploy")
@dataclass
class Deploy(Intent):
    """部署基地车。"""

    units: tuple[int, ...] = ()


@register("produce")
@dataclass
class Produce(Intent):
    """要求开始生产某类型，直到工厂产出或意图终止。

    `type_pointer` 是 `ObjectTypeClass` 的指针，由类型表解析得到。
    """

    type_pointer: int = 0
    type_name: str = ""


@register("place")
@dataclass
class Place(Intent):
    """把已完工的建筑放到指定格。

    `cell` 可以**不给**：建筑能不能放在某格只有引擎说了算（本地算出来的「空地」
    会被 `CanPlaceHere` 拦下），故 `None` 表示「交给 L0 问 `PlaceQuery` 要一格
    最近的合法落点」。模型因此不必自己算坐标，也不必猜。
    """

    building: int = 0
    cell: tuple[int, int] | None = None


@register("sell")
@dataclass
class Sell(Intent):
    """变卖建筑。对象级网络事件，L0 会走 `ClickEvent`。"""

    buildings: tuple[int, ...] = ()


@register("wake")
@dataclass
class Wake(Intent):
    """请求唤醒模型，附一句说明。

    **它不落到引擎**——没有对应的引擎命令，`Executor` 处理不了。技法层会把它拦下来
    交给桥接层，其余意图照常下发。

    它仍是意图：带信封、可记录、可回放，与其余意图同构。
    """

    text: str = ""


def split_wakes(intents) -> tuple:
    """把一批意图分成 `(给引擎的, 唤醒用的)`。

    技法只返回意图，不自己发命令；分辨哪条往下走、哪条往上走是技法层的活。
    """
    engine, wakes = [], []
    for intent in intents:
        (wakes if isinstance(intent, Wake) else engine).append(intent)
    return tuple(engine), tuple(wakes)


@register("call")
@dataclass
class TacticCall(Intent):
    """指挥层意图：调用一条技法，由技法层展开成给基础设施的意图。

    载荷通用（技法名加参数），使模型新增技法不必改 schema；参数按技法声明的
    `Param` 在调用前校验。
    """

    tactic: str = ""
    params: dict = field(default_factory=dict)
    layer: Layer = Layer.L2_COMMAND


# ---------------------------------------------------------------- 决策日志
@dataclass(frozen=True)
class DecisionRecord:
    """决策日志的一条。

    只记决策与命令结果，不记观测——单帧 11.9 KB 无法逐帧留存，且可由录制文件
    复现。`facts` 保存该决策依据的事实摘要，使归因不必翻原始状态。
    """

    frame: int
    event: str
    intent_id: str | None = None
    layer: int | None = None
    detail: dict | None = None
    facts: dict | None = None
    at: float = field(default_factory=time.time)


class DecisionLog:
    """追加写的 JSONL 决策日志，一局一个文件，以游戏帧为主键。"""

    def __init__(self, path):
        self.path = path
        self._handle = open(path, "a", encoding="utf-8")

    def record(self, frame, event, intent=None, detail=None, facts=None):
        """写入一条记录。`intent` 可为 `Intent` 实例。"""
        entry = DecisionRecord(
            frame=frame, event=event,
            intent_id=getattr(intent, "id", None),
            layer=int(intent.layer) if intent is not None else None,
            detail=detail, facts=facts)
        self._handle.write(json.dumps(asdict(entry), ensure_ascii=False,
                                      sort_keys=True) + "\n")
        self._handle.flush()
        return entry

    def close(self):
        """关闭日志文件。"""
        self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def frames_for(seconds: float, fps: float = NOMINAL_FPS) -> int:
    """把人类口述的秒数换算为游戏帧数。

    引擎时钟是帧，故 TTL 一律以帧存储；人类给出的时长在发出意图时换算一次。
    """
    return max(1, int(round(seconds * fps)))
