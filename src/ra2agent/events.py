"""把观测流合成成事件。

事件是**数据**，不是回调——与意图同构，便于记录、回放与人工编辑。

**只在两帧之间做差**，故本模块是纯函数：同样的前后帧永远给出同样的事件。这是
离线闭环能验证「事件触发的技法」的前提——回放场景存的是原始帧，事件可以重新合成。

**尊重迷雾**：只用 `Observation`（已按阵营与迷雾过滤），以及全图公开的那几样
（`House.defeated` 是公开信息——谁被打死了所有人都知道）。**不读敌方的
`power` / `money` / `infiltrated`**——那些是内部状态。

选哪些事件、为什么，见 `corpus/notes/eva_needed.md`。
"""
import collections
import dataclasses
import itertools
from dataclasses import dataclass
from enum import Enum

#: 「资金不足」的判据：余额跌破这个数。引擎的判据是「下单时钱不够」，
#: 那要读类型表与前提，见 `corpus/notes/eva_needed.md` 的待办。
DEFAULT_FUNDS_THRESHOLD = 200

#: 三方渗透的顺序与 `House` 上的字段名。
INFILTRATION_SIDES = (("allied", "allied_infiltrated"),
                      ("soviet", "soviet_infiltrated"),
                      ("third", "third_infiltrated"))


#: 给模型看的名字。
KIND_LABEL = {}


class EventKind(str, Enum):
    """事件类型。取值即稳定标识，写进日志与配置。"""

    LOW_POWER = "low_power"
    INSUFFICIENT_FUNDS = "insufficient_funds"
    INFILTRATED = "infiltrated"
    PLAYER_DEFEATED = "player_defeated"
    #: 己方对象**从地图上消失**（被打掉）。完工待放置的那一栋不算——它只是进了
    #: limbo，指针还在。
    OBJECT_LOST = "object_lost"
    #: 新出现一栋**完工待放置**的建筑。放哪儿是模型的事（「电厂往矿区那边放」
    #: 这类判断），故要把它叫回来看一眼。
    PLACEMENT_READY = "placement_ready"


KIND_LABEL.update({
    EventKind.LOW_POWER: "电力不足",
    EventKind.INSUFFICIENT_FUNDS: "资金不足",
    EventKind.INFILTRATED: "被渗透",
    EventKind.PLAYER_DEFEATED: "玩家出局",
    EventKind.OBJECT_LOST: "损失单位/建筑",
    EventKind.PLACEMENT_READY: "建筑完工待放置",
})


@dataclass(frozen=True)
class Subject:
    """事件关于谁。

    凡是关于「谁」的事件都必须带主语——不带主语的「有玩家被击败」没有用。
    """

    kind: str                 # "house"
    id: int                   # 阵营的 array_index，稳定且可读
    name: str
    faction: str = ""
    is_human: bool = False
    is_you: bool = False

    def render(self) -> str:
        """给人看的一句话。"""
        who = self.name or self.faction or f"#{self.id}"
        tags = []
        if self.is_you:
            tags.append("你")
        elif self.is_human:
            tags.append("人类")
        else:
            tags.append("电脑")
        if self.faction and self.faction != who:
            tags.append(self.faction)
        return f"{who}（{'，'.join(tags)}）"


@dataclass(frozen=True)
class Event:
    """一帧观测与上一帧之间的一个变化。"""

    kind: EventKind
    frame: int
    subject: Subject
    data: dict = dataclasses.field(default_factory=dict)

    def render(self) -> str:
        """给人看的一句话。"""
        if self.kind is EventKind.LOW_POWER:
            return f"电力不足（{self.data.get('drain')}/{self.data.get('output')}）"
        if self.kind is EventKind.INSUFFICIENT_FUNDS:
            return f"资金不足（剩 {self.data.get('money')}）"
        if self.kind is EventKind.INFILTRATED:
            return f"被{self.data.get('side_label', '')}渗透"
        if self.kind is EventKind.PLAYER_DEFEATED:
            return f"{self.subject.render()} 被击败"
        if self.kind is EventKind.OBJECT_LOST:
            names = "、".join(self.data.get("names", ())) or "对象"
            return f"损失 {self.data.get('count', 1)} 个：{names}"
        if self.kind is EventKind.PLACEMENT_READY:
            names = "、".join(self.data.get("names", ())) or "建筑"
            return f"完工待放置：{names}"
        return self.kind.value


@dataclass(frozen=True)
class Policy:
    """事件判据里可调的部分。"""

    #: 余额跌破它就报「资金不足」。
    funds_threshold: int = DEFAULT_FUNDS_THRESHOLD


class EventLog:
    """事件队列。

    **记录与投递分开**：队列留下全部事件（有上限），而给模型的那一份按窗口聚合。
    合并只影响投递，不影响留痕——复盘时仍有全量可查。

    喂帧是**幂等**的：同一帧喂两次不会重复报。`tick()` 与 `status()` 都可能触发读帧，
    都挂在 `Observer.poll()` 后面，靠这条保证不重复。
    """

    def __init__(self, capacity=256, policy=None):
        self.capacity = capacity
        self.policy = policy or Policy()
        self._events = collections.deque(maxlen=capacity)
        #: 累计记录过多少条。游标基于它，故被上限挤掉也不会错位。
        self._total = 0
        self._last = None

    def update(self, observation) -> tuple:
        """喂一帧观测，返回这一拍新产出的事件。"""
        if observation is None:
            return ()
        if self._last is not None and observation.frame == self._last.frame:
            return ()
        events = detect(self._last, observation, self.policy)
        self._last = observation
        self.record(events)
        return events

    def record(self, events) -> None:
        """直接记入若干事件，不经检测。"""
        self._events.extend(events)
        self._total += len(events)

    def __len__(self):
        return self._total

    def new_since(self, cursor) -> tuple:
        """`cursor` 之后的全部事件。

        返回 `(事件, 新游标)`。被上限挤掉的那些取不回来，故游标会被夹到现有的起点。
        """
        oldest = self._total - len(self._events)
        skipped = max(cursor, oldest) - oldest
        return tuple(itertools.islice(self._events, skipped, None)), self._total


#: 投递时每类最多列几条，其余折成计数。
MAX_LISTED_PER_KIND = 4


def summarize(events) -> str:
    """把一批事件合成给模型看的一段。

    同类合并、同类里再按主语去重。**只影响投递**——队列里仍是全量。
    """
    if not events:
        return ""
    groups = collections.OrderedDict()
    for event in events:
        groups.setdefault(event.kind, []).append(event)
    lines = []
    for kind, group in groups.items():
        lines.append(f"- {KIND_LABEL.get(kind, kind.value)} ×{len(group)}")
        seen = set()
        for event in group:
            detail = event.render()
            if kind is not EventKind.PLAYER_DEFEATED:
                detail = detail.split("（")[0]
            if detail in seen:
                continue
            seen.add(detail)
            if len(seen) > MAX_LISTED_PER_KIND:
                lines.append(f"  - …另有 {len(group) - MAX_LISTED_PER_KIND} 条")
                break
            lines.append(f"  - {detail}")
    return "\n".join(lines)


def subject_of(house, me=None) -> Subject:
    """由一个 `House` 造出事件主语。"""
    return Subject(kind="house", id=house.array_index, name=house.name,
                   faction=house.faction, is_human=house.is_human_player,
                   is_you=me is not None and house.pointer == me.pointer)


def detect(before, after, policy=None) -> tuple:
    """`before` 到 `after` 之间发生了什么。`before` 为 `None` 时报空。

    第一帧没有「之前」，故不报——当前局面由本局简报负责，那不是事件。
    """
    if before is None or after is None:
        return ()
    policy = policy or Policy()
    events = []
    me = after.house

    events += _detect_low_power(before.house, me, after.frame, policy)
    events += _detect_funds(before.house, me, after.frame, policy)
    events += _detect_infiltration(before.house, me, after.frame, policy)
    events += _detect_losses(before, after, policy)
    events += _detect_placement(before, after, policy)
    events += _detect_defeats(before, after, me, policy)
    return tuple(events)


def _detect_placement(before, after, policy):
    """**新**出现一栋完工待放置的建筑时报一次。

    放哪儿是模型的事（往矿区那边放、还是先占住路口），所以这条要能把它叫回来。
    已经报过的（上一帧就在 limbo 里）不再报——否则每拍都会叫一次。
    """
    if after.state is None or before.state is None:
        return ()
    fresh = []
    for obj in after.state.own_objects():
        if not obj.in_limbo:
            continue
        old = before.state.object(obj.pointer)
        if old is not None and old.in_limbo:
            continue                     # 上一帧就在等放置，不是新事
        fresh.append(obj)
    if not fresh:
        return ()
    types = getattr(after, "types", None)
    names = []
    for obj in fresh:
        name = types.name(obj, "") if types is not None else ""
        if name and name not in names:
            names.append(name)
    return (Event(kind=EventKind.PLACEMENT_READY, frame=after.frame,
                  subject=subject_of(after.house, after.house),
                  data={"count": len(fresh), "names": tuple(names)}),)


def _detect_losses(before, after, policy):
    """己方对象从地图上消失时报一次。

    **判据是「指针不在这一帧的对象表里」**，不是「不在 `own` 里」：建筑完工待放置
    时会进 limbo、从 `own` 里消失，但指针还在——那是去放置，不是被打掉。
    """
    if after.state is None or not before.own:
        return ()
    lost = [obj for obj in before.own
            if after.state.object(obj.pointer) is None]
    if not lost:
        return ()
    types = getattr(after, "types", None)
    names = []
    for obj in lost:
        name = types.name(obj, "") if types is not None else ""
        if name and name not in names:
            names.append(name)
    return (Event(kind=EventKind.OBJECT_LOST, frame=after.frame,
                  subject=subject_of(after.house, after.house),
                  data={"count": len(lost), "names": tuple(names)}),)


def _detect_low_power(before, after, frame, policy):
    """电力由够用变成入不敷出时报一次；恢复不报。"""
    if before.is_low_power or not after.is_low_power:
        return ()
    return (Event(kind=EventKind.LOW_POWER, frame=frame,
                  subject=subject_of(after, after),
                  data={"drain": after.power_drain, "output": after.power_output}),)


def _detect_funds(before, after, frame, policy):
    """余额跌破阈值的瞬间报一次。"""
    if before.money < policy.funds_threshold or after.money >= policy.funds_threshold:
        return ()
    return (Event(kind=EventKind.INSUFFICIENT_FUNDS, frame=frame,
                  subject=subject_of(after, after),
                  data={"money": after.money, "threshold": policy.funds_threshold}),)


def _detect_infiltration(before, after, frame, policy):
    """三方渗透各自的标志由假变真时报一次。

    引擎只给「当前是否处于被渗透状态」，**看不出渗透了什么**（科技、雷达、资金、
    电力），也看不出「被渗透了几次」。故这里只能按方报。
    """
    events = []
    for side, field in INFILTRATION_SIDES:
        if getattr(before, field) or not getattr(after, field):
            continue
        events.append(Event(kind=EventKind.INFILTRATED, frame=frame,
                            subject=subject_of(after, after),
                            data={"side": side,
                                  "side_label": {"allied": "盟军", "soviet": "苏军",
                                                 "third": "尤里"}[side]}))
    return tuple(events)


def _detect_defeats(before, after, me, policy):
    """有玩家由未出局变成出局。带主语——不带就没有用。"""
    was = _defeated_ids(before) if before.state else set()
    events = []
    for house in (after.state.houses if after.state else ()):
        if house.is_neutral or not house.defeated or house.array_index in was:
            continue
        events.append(Event(kind=EventKind.PLAYER_DEFEATED, frame=after.frame,
                            subject=subject_of(house, me)))
    return tuple(events)


def _defeated_ids(observation):
    """上一帧里已经出局的阵营。"""
    if observation.state is None:
        return set()
    return {h.array_index for h in observation.state.houses if h.defeated}
