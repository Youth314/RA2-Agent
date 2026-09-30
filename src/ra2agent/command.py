"""指挥层：模型与技法层之间的那道门。

模型只看见四件事——读局势、读卡片、下达、撤销。**工具数固定，能力数随技法库
增长**：库里可以有几百条技法，模型看到的永远只是这四扇门，门里的东西写在卡片上。

本模块不含策略，也不碰引擎：它把技法层的能力包成稳定的调用面，MCP 服务与假模型
脚本都只是它的薄壳。契约见 `.agents/notes/指挥层.md`。

受理请求时先做一遍技法层同样的校验（参数、等级、适用条件、单位归属），使模型当场
拿到「这条用不上、参数不对」，而不是等一拍之后静默失败。
"""
from dataclasses import dataclass, field

from .runtime.autopilot import Autopilot
from .data.catalogue import (MAX_BUILDABLE_BUILDINGS, MAX_BUILDABLE_UNITS,
                        own_building_cells, owned_building_ids, stolen_labels,
                        water_nearby)
from .constants import (LandType, PLACE_QUERY_MAX_LENGTH, PLACE_SITE_RADIUS)
from .errors import Ra2Error, TacticError
from .engine.events import summarize
from .runtime.formation import place_candidates
from .runtime.intents import Scope, TacticCall
from .engine.state import cell_center
from .tactics import Mode
from .tactics.conditions import explain

#: 撤销不了的返回文案。
UNKNOWN_INTENT = "没有这条在管任务：可能已结束或被撤销"


#: 引擎原文 → 给模型的一句「可能是什么原因」。
#:
#: 引擎拒得含糊（`unbuildable object_type { pointer_self: 288526200 … }`——那串每次
#: 都不同的数字是内存地址），我们改不了它，但可以让模型知道该往哪儿查，而不是
#: 对着这句话发愣、拿同一条废单反复试。
REASON_HINTS = (
    ("unbuildable",
     "引擎没说原因。常见三种：前提没到（矿厂/兵营/重工等）、钱不够、科技等级不够"
     "——用 status 的「可造」段逐项核对，别重复下同一单"),
    ("not found from any factory",
     "这栋建筑已经不在任何工厂里了：多半是同一栋楼被两条放置任务抢着放，先看"
     "status 的「待放置」还在不在"),
    ("proximity check failed",
     "落点被引擎判为放不下：别自己猜格，用 status 的「可选落点」里的一格，或直接"
     "不给 cell 让 L0 问引擎要"),
    ("invalid cell",
     "目标格不可通行（水/岩石/墙）或在地图外——收手就行，换一格"),
)


def reason_hint(reason) -> str:
    """按引擎原文给一句排查方向；认不出来就给空串。"""
    text = (reason or "").lower()
    for needle, hint in REASON_HINTS:
        if needle in text:
            return hint
    return ""


def is_notable(record) -> bool:
    """自动执行的记录值不值得报给模型。"""
    return bool(record.get("outcomes") or record.get("error") or record.get("paused"))


def describe_auto(record) -> str:
    """一行说清自动层干了什么。"""
    name = record.get("tactic", "?")
    if record.get("error"):
        return f"{name}｜失败：{record['error']}"
    if record.get("paused"):
        return f"{name}｜挂起：{record['paused']}"
    parts = []
    for outcome in record.get("outcomes", ()):
        if outcome.get("error"):
            parts.append(f"{outcome['intent']} 失败")
        else:
            parts.append(f"{outcome['intent']} {outcome.get('state', '')}".strip())
    return f"{name}｜" + "、".join(parts)


def describe_wake(record) -> str:
    """一行说清一条唤醒为什么没送到。"""
    reason = record.get("error") or record.get("skipped") or record.get("deferred") or "未送达"
    text = (record.get("text") or "").strip().splitlines()[0][:40] if record.get("text") else ""
    return f"{reason}｜{text}" if text else reason


def observation_events(observer, cursor):
    """`observer` 上自 `cursor` 起的新事件，返回 `(事件, 新游标)`。

    没挂事件队列的观测者给出空——测试里的假件就是如此。
    """
    log = getattr(observer, "events", None)
    if log is None:
        return (), cursor
    return log.new_since(cursor)


def describe_map(map_data):
    """地图尺寸与水域占比；还没取到地图返回空串。

    水域占比是目前判断海战图的唯一现成线索——`GameSettings`（含 `map_name` 与
    `game_mode`）在引擎的 proto 里有定义，但上游一处都没实现，取不到。
    """
    if map_data is None:
        return ""
    lands = map_data.columns.get("land_type") or ()
    water = sum(1 for value in lands if value == LandType.WATER)
    ratio = water * 100.0 / len(lands) if lands else 0.0
    return f"地图 {map_data.width}×{map_data.height}，水域 {ratio:.0f}%"


def describe_houses(state):
    """参战各方：名字、是不是你、**国家**、出局没有、**赢了没有**。

    国家取 `House.faction`（探针给的是引擎的 HouseType ID，如 `Americans`）——
    它决定特有兵种与建筑，此前只是没渲染出来，模型只能从 `side` 猜。

    胜负要能读出来：**一局的终点就是这里**，模型得知道自己该继续还是收工。引擎在
    出局与获胜时各置一个标志，单看哪个都不够（残局里对手可能还在），故原样报出来。
    """
    parts = []
    for house in state.houses:
        if house.is_neutral:
            continue
        who = "你" if house.current_player else ("人类" if house.is_human_player else "电脑")
        if house.defeated:
            who += "，已出局"
        if house.is_winner:
            who += "，已获胜"
        if house.is_loser:
            who += "，判负"
        country = f"，{house.faction}" if house.faction else ""
        parts.append(f"{house.name}（{who}{country}）")
    return f"参战 {len(parts)} 方｜" + " · ".join(parts) if parts else ""


#: 一次最多列多少个单位，免得文本长到把上下文吃掉。
MAX_LISTED_UNITS = 24

#: 电厂一类建筑的生产步数：`progress_timer` 走到这里即完工（实测 Allied Power Plant）。
PRODUCTION_STEPS = 54

#: 一个落点集最多给模型看几个。查出来的合法格可达几十个，全给只会淹掉上下文。
MAX_LISTED_SITES = 12

#: 落点集缓存多少帧。`PlaceQuery` 是一次真机往返，不该每次读局势都查。
PLACE_SITES_TTL_FRAMES = 22


def describe_production(factory, state, types) -> str:
    """一条生产记录：在造什么、进度、是否完工待放、是否暂停。

    **在造的类型引擎确实给了**：`Factory.queued_objects` 是对象指针元组，而同一个
    对象就在这一帧的 `state.objects` 里（测绘结果：工厂内的对象即落成后的对象，
    指针从生产到放置不变）。故拿指针回查类型即可，不必给 `Factory` 新增字段。
    """
    names = []
    for pointer in factory.queued_objects:
        queued = state.object(pointer) if state is not None else None
        names.append(types.name(queued, "?") if types is not None and queued
                     else "?")
    if not names and state is not None and types is not None:
        # 建造厂造建筑时 `queued_objects` **一直是空的**：产出物只挂在 limbo 里。
        # 不回查它，这一行就会写成「队列为空｜进度 54/54（完工待放置）」，自相矛盾，
        # 实测两个测试员都把它当成了「队列显示不全」。只在确实有 limbo 产出物时补，
        # 免得把单位工厂的闲置状态误报成在造它自己。
        pending = state.object(factory.object)
        if pending is not None and pending.in_limbo:
            names.append(types.name(pending, "?"))
    what = "、".join(names) if names else "队列为空"
    progress = f"{factory.progress_timer}/{PRODUCTION_STEPS}"
    marks = []
    if factory.completed:
        marks.append("完工待放置")
    if factory.on_hold:
        marks.append("已暂停")
    mark = f"（{'，'.join(marks)}）" if marks else ""
    return f"- {what}｜进度 {progress}{mark}"


def describe_placement(agent_id, factory, state, types) -> str:
    """一行说清「手上有一栋待放置的建筑」。

    **不报坐标**：建筑还没落地，它自己报的格是 `(0,0)` 或建造厂的位置（实测两种
    都出现过，还会在两拍之间自己漂），与「该放哪儿」无关。写上去只会被读成落点
    ——真正的落点在下面的「可选落点」里。
    """
    building = state.object(factory.object) if state is not None else None
    name = types.name(building, "?") if types is not None and building else "?"
    return f"- #{agent_id}｜{name}｜等待放置"


def describe_cells(cells) -> str:
    """把若干格写成 `(x,y)、(x,y)`。"""
    return "、".join(f"({x},{y})" for x, y in cells)


def bearing_of(center, cell) -> str:
    """`cell` 在 `center` 的哪一侧。格坐标 x 向东为正、y 向南为正。

    粗略取八向：主轴明显（超过 2:1）就报正方向，否则报斜向。模型读「西侧 3 格」
    比读 `(107,61)` 省事——**省掉算坐标的心智**正是这段的意义。
    """
    dx, dy = cell[0] - center[0], cell[1] - center[1]
    if dx == 0 and dy == 0:
        return "原地"
    if dy == 0:
        return "东" if dx > 0 else "西"
    if dx == 0:
        return "南" if dy > 0 else "北"
    if abs(dx) > 2 * abs(dy):
        return "东" if dx > 0 else "西"
    if abs(dy) > 2 * abs(dx):
        return "南" if dy > 0 else "北"
    ew = "东" if dx > 0 else "西"
    ns = "南" if dy > 0 else "北"
    return ew + ns


def describe_bearings(center, sites, top=4) -> str:
    """按相对基地的方位与距离概括一组落点，多的折成计数。"""
    if center is None or not sites:
        return "方位未知"
    groups = {}
    for cell in sites:
        groups.setdefault(bearing_of(center, cell), []).append(cell)
    parts = []
    for name, cells in sorted(groups.items(), key=lambda item: (-len(item[1]),
                                                                item[0]))[:top]:
        spans = [max(abs(c[0] - center[0]), abs(c[1] - center[1])) for c in cells]
        span = (f"{spans[0]}" if min(spans) == max(spans)
                else f"{min(spans)}–{max(spans)}")
        parts.append(f"{name} {len(cells)} 格（{span} 格外）")
    return "·".join(parts)


def _unit_line(item) -> str:
    """一个单位一行：id、名字、格，以及它是不是已经在某条任务里。"""
    state = f"在管 {item['tactic']}" if item.get("tactic") else "空闲"
    return f"- {item['id']}｜{item['name']}｜格 ({item['cell'][0]},{item['cell'][1]})｜{state}"


class UnitPool:
    """适用条件用的一队单位视图：此刻己方全部可用单位当成一队。

    `tactics` 与 `call` 在还没建编队时也要评适用条件，故给它一个临时 subject。

    **完工待放置的建筑在 `observation.own` 里不存在**——观测把 `in_limbo` 的己方
    对象整个丢掉了（[observation.py:116](observation.py)）。但技法需要能拿它的
    agent id 才能发 `Place`，故这里额外收一份 `_pending`：可寻址，但**不算可用
    单位**，`agents()` 不报它，它也不会被塞进意图的默认 scope。
    """

    def __init__(self, observation, identity):
        self.observation = observation
        self.identity = identity
        self._own = {}
        self._pending = {}
        state = observation.state
        # 从 state 取而不是从 observation.own 取：后者已经滤掉 limbo 对象
        for obj in (state.own_objects() if state is not None else ()):
            agent = identity.agent_id(obj.pointer)
            if agent is None:
                continue
            (self._pending if obj.in_limbo else self._own)[agent] = obj
        # 待放置的先建，在地图上的后建——同指针时以「在地图上」为准
        self._pointers = {obj.pointer: agent for agent, obj in self._pending.items()}
        self._pointers.update({obj.pointer: agent for agent, obj in self._own.items()})

    def agents(self) -> tuple:
        """己方全部可用单位的 agent id。不含待放置的建筑。"""
        return tuple(self._own)

    def object_of(self, agent_id):
        """按 agent id 取对象。"""
        return self._own.get(agent_id)

    def pending(self) -> tuple:
        """己方待放置（`in_limbo`）对象的 agent id。"""
        return tuple(self._pending)

    def buildings(self) -> tuple:
        """己方在地图上的建筑。落点查询拿它们当候选中心。"""
        return tuple(obj for obj in self._own.values() if obj.is_building)

    def agent_id(self, pointer):
        """引擎指针转 agent id。含待放置的建筑——`Place` 只收 agent id。"""
        return self._pointers.get(pointer)

    def cell_of(self, agent_id):
        """按 agent id 取所在格。"""
        found = self.object_of(agent_id)
        return found.coordinates.cell if found else None


@dataclass(frozen=True)
class CallRequest:
    """一条下达请求：调哪条技法、作用于哪些单位、参数与有效期。"""

    tactic: str
    units: tuple = ()
    params: dict = field(default_factory=dict)
    ttl_frames: int | None = None


@dataclass(frozen=True)
class CallResult:
    """一条下达请求的受理结果。受理不等于成功：成功与否由后续的 `status` 报。"""

    accepted: bool
    tactic: str
    intent_id: str | None = None
    error: str = ""

    def render(self) -> str:
        """一行结果文本。"""
        if self.accepted:
            return f"已受理 {self.tactic}#{self.intent_id}"
        return f"未受理 {self.tactic}：{self.error}"


@dataclass(frozen=True)
class StatusReport:
    """模型每次醒来先看的东西：局势、单位、在管任务、它上次之后发生的事。

    `units` 与 `enemies` 给的是事实（id、名字、所在格、是否已在任务里），不含建议；
    模型没有这些就无从指定落点。
    """

    frame: int
    summary: str
    #: 每拍都带的极短一行：地图与参战方。
    match: str = ""
    #: 首次进入对局时报一次的本局简报；之后为空。
    brief: str = ""
    #: 上次读走之后新结算的任务。
    results: tuple = ()
    #: 上次读走之后的新事件；读走即清空游标。
    events: tuple = ()
    #: 自动触发层做成或失败的事。空转与没触发的不在其中。
    auto: tuple = ()
    #: **没送出去**的唤醒。送成功的不报——那条消息本身就是通知。
    wakes: tuple = ()
    units: tuple = ()
    enemies: tuple = ()
    running: tuple = ()
    #: 电力一行；还没进对局时为空。
    power: str = ""
    #: 生产队列，每个工厂一行；无工厂时为空。
    production: tuple = ()
    #: 完工待放置的建筑，每栋一行。
    placement: tuple = ()
    #: 待放置几**栋**。`placement` 现在是逐行文本（含方位子行），栋数单独记。
    placement_count: int = 0
    #: 建筑待放置但拿不到落点集时的说明；拿到了则为空。
    placement_note: str = ""
    #: 当前可选落点（格坐标）。由模型挑一个，作为 `place_ready_building` 的参数。
    sites: tuple = ()
    #: 「现在能造什么、还缺什么」。每行一类（建筑 / 单位）。空表示目录没读到。
    buildable: tuple = ()
    notices: tuple = ()

    def render(self) -> str:
        """渲染成模型读的文本，形状稳定、尽量短。"""
        lines = [f"局势｜{self.summary}"]
        if self.brief:
            lines.extend(self.brief.splitlines())
        elif self.match:
            lines.append(self.match)
        if self.events:
            lines.append(f"新事件 {len(self.events)} 条：")
            lines.extend(summarize(self.events).splitlines())
        if self.auto:
            lines.append(f"自动层 {len(self.auto)} 项：")
            lines.extend(f"- {describe_auto(record)}" for record in self.auto)
        if self.wakes:
            lines.append(f"唤醒未送达 {len(self.wakes)} 条：")
            lines.extend(f"- {describe_wake(record)}" for record in self.wakes)
        if self.power:
            lines.append(f"电力｜{self.power}")
        if self.production:
            lines.append(f"生产 {len(self.production)} 线：")
            lines.extend(self.production)
        if self.placement:
            lines.append(f"待放置 {self.placement_count or len(self.placement)} 栋：")
            lines.extend(self.placement)
            if self.sites:
                lines.append("- 用 call place_ready_building 指定一格"
                             "（参数 cell，形如 [x,y]）；不给 cell 则由 L0 问引擎要")
            elif self.placement_note:
                lines.append(f"- 落点未知：{self.placement_note}")
        if self.buildable:
            lines.append("可造（✓ 现在就能造；✗ 后面是还缺的前提）：")
            lines.extend(self.buildable)
        if self.units:
            lines.append(f"己方单位 {len(self.units)}：")
            for unit in self.units[:MAX_LISTED_UNITS]:
                lines.append(_unit_line(unit))
            if len(self.units) > MAX_LISTED_UNITS:
                lines.append(f"- …另有 {len(self.units) - MAX_LISTED_UNITS} 个未列出")
        if self.enemies:
            lines.append(f"可见敌方 {len(self.enemies)}：")
            for enemy in self.enemies[:MAX_LISTED_UNITS]:
                lines.append(_unit_line(enemy))
        else:
            lines.append("可见敌方：无")
        if self.running:
            lines.append(f"在管 {len(self.running)} 项：")
            for item in self.running:
                modes = "、".join(f"{name} {count}"
                                  for name, count in sorted(item["modes"].items()))
                elapsed = self.frame - item["created_frame"]
                lines.append(f"- {item['tactic']}#{item['intent_id']}｜"
                             f"单位 {','.join(str(u) for u in item['units'])}｜"
                             f"{modes}｜已 {elapsed} 帧")
        else:
            lines.append("在管 0 项")
        if self.results:
            lines.append(f"新结果 {len(self.results)} 条：")
            for event in self.results:
                line = (f"- {event['tactic']}#{event['intent_id']}｜{event['state']}｜"
                        f"到位 {len(event['arrived'])} 损失 {len(event['lost'])} "
                        f"失败 {len(event['failed'])}")
                if event.get("reason"):
                    # 只有失败了才值得说原因；成功的那一行不塞噪声
                    line += f"｜原因：{event['reason']}"
                    hint = reason_hint(event["reason"])
                    if hint:
                        line += f"｜{hint}"
                lines.append(line)
        if self.notices:
            lines.append(f"告警 {len(self.notices)} 条：")
            for notice in self.notices:
                lines.append(f"- {notice['kind']}（帧 {notice['frame']}）"
                             f"｜{notice['detail']}")
        return "\n".join(lines)


#: 房子级动作要点名谁。这些技法不针对具体单位，但任务仍得挂在某个己方对象上。
HOUSE_LEVEL = {
    "build_structure": "建造厂",
    "place_ready_building": "建造厂（或生产它的那个厂）",
    "train_unit": "对应的生产建筑",
}


class Commander:
    """四个工具的实体。MCP 服务与脚本都只是它的适配器。"""

    def __init__(self, layer, observer, log=None):
        self.layer = layer
        self.observer = observer
        self.registry = layer.registry
        self.log = log
        self._seen_completed = 0
        self._seen_notices = 0
        self._briefed = False
        self._seen_events = 0
        self._auto_cursor = 0
        self._seen_auto = 0
        self._seen_wakes = 0
        #: 落点集缓存。`PlaceQuery` 是一次真机往返，不该每次读局势都查。
        #: 落点集缓存：建筑指针 → `(帧, 落点, 说明)`。**一栋一份**——不同建筑
        #: 占地不同，引擎给的合法格也不同。
        self._sites_cache: dict = {}
        #: 自动触发层。技法按名片里的触发声明自己跑，产出的是脉冲。
        # 唤醒桥挂在技法层上：一个会话一份额度，自动层与模型调用的路径共用
        self.autopilot = Autopilot(layer.registry, layer.executor, log=log,
                                   wake=layer.wake)

    # ------------------------------------------------------------ 工具一：局势
    def status(self, observation=None) -> StatusReport:
        """读局势：一行摘要、在管任务、以及上次读过之后的新结果与告警。

        新结果只报一次：读走即清空，免得模型每拍都重看同一批。

        **游标最后才推**：上面任何一步抛了，这批新结果仍在游标之后，下次读还能拿到。
        先前是先推游标再渲染，于是渲染路上崩一次（实测 `int(House)`）就把那批结果
        永久吞掉——「只报一次」不该变成「不报也不留」。
        """
        observation = observation if observation is not None else self.observer.poll()
        completed = self.layer.completed[self._seen_completed:]
        notices = self.layer.notices[self._seen_notices:]
        match, brief = self._match_info(observation)
        new_events, seen_events = observation_events(self.observer, self._seen_events)
        auto, seen_auto = self.auto_records(self._seen_auto)
        wakes, seen_wakes = self.wake_records(self._seen_wakes)
        pool = self._pool(observation)
        placement, placement_note, sites = self._placement(observation, pool)
        report = StatusReport(
            frame=observation.frame, summary=observation.summary(),
            match=match, brief=brief, events=new_events, auto=auto, wakes=wakes,
            power=self._power(observation),
            production=self._production(observation),
            placement=placement, placement_note=placement_note,
            placement_count=len(self._completed_factories(observation.state)),
            sites=sites,
            buildable=self._buildable(observation),
            units=self._own_units(observation),
            enemies=self._enemy_units(observation),
            running=self.layer.progress(), results=tuple(completed),
            notices=tuple(notices))
        self._seen_completed = len(self.layer.completed)
        self._seen_notices = len(self.layer.notices)
        self._seen_events = seen_events
        self._seen_auto = seen_auto
        self._seen_wakes = seen_wakes
        return report

    # ------------------------------------------------------------ 电力与生产
    @staticmethod
    def _power(observation) -> str:
        """电力一行。`power_output/power_drain` 早已解析，此前没有任何地方报它。"""
        house = observation.house
        if house is None:
            return ""
        text = f"{house.power_drain}/{house.power_output}"
        return f"{text}｜电力不足" if house.is_low_power else text

    def _production(self, observation) -> tuple:
        """生产队列，每个己方工厂一行：在造什么、进度、是否待放置。"""
        state = observation.state
        if state is None:
            return ()
        types = getattr(self.observer, "types", None)
        return tuple(describe_production(factory, state, types)
                     for factory in state.own_factories())

    # ------------------------------------------------------------ 待放置与落点
    def _placement(self, observation, pool) -> tuple:
        """完工待放置的建筑，以及**每栋各自**的可选落点。

        返回 `(行, 拿不到落点时的说明, 全部落点)`。合法格只有引擎说了算，故这里替
        模型问 `PlaceQuery`——**结果按帧、按建筑缓存**，不然每次读局势都要一次真机
        往返。

        **必须一栋一问**：不同建筑占地不同，引擎给的合法格也不同。以前只问第一栋，
        第二栋的落点就跟着第一栋的列表一起显示（实测被报成「2×2 与 3×3 混着给」）。
        """
        state = observation.state
        factories = self._completed_factories(state)
        if not factories:
            self._forget_sites()
            return (), "", ()
        types = getattr(self.observer, "types", None)
        center = self._base_center(state, types)
        lines, notes, every = [], [], []
        for factory in factories:
            agent = pool.agent_id(factory.object)
            lines.append(describe_placement(agent if agent is not None else "?",
                                            factory, state, types))
            sites, note = self._sites_for(observation, factory, pool)
            every.extend(sites)
            if sites:
                lines.append(f"  - 可选落点 {len(sites)} 格："
                             f"{describe_bearings(center, sites)}"
                             f"｜例如 {describe_cells(sites[:4])}")
            else:
                lines.append(f"  - 落点未知：{note}")
                notes.append(note)
        return tuple(lines), "；".join(notes), tuple(every)

    @staticmethod
    def _completed_factories(state):
        """已完工、等玩家放置的那些工厂条目。"""
        if state is None:
            return ()
        return tuple(factory for factory in state.own_factories() if factory.completed)

    def _base_center(self, state, types):
        """方位参照点：建造厂所在格；没有就取己方建筑的中心。

        模型读「西侧 3 格」比读 `(107,61)` 省事，而「西」是相对基地说的。
        """
        cells = [obj.coordinates.cell for obj in state.own_objects()
                 if obj.is_building and not obj.in_limbo]
        if not cells:
            return None
        if types is not None:
            for obj in state.own_objects():
                if obj.in_limbo or not obj.is_building:
                    continue
                name = types.name(obj, "")
                if "construction yard" in name.lower():
                    return obj.coordinates.cell
        return (sum(c[0] for c in cells) // len(cells),
                sum(c[1] for c in cells) // len(cells))

    def _sites_for(self, observation, factory, pool) -> tuple:
        """取（或复用缓存的）某一栋的合法落点集。"""
        pointer = factory.object
        frame = observation.frame
        cached = self._sites_cache.get(pointer)
        if cached is not None and frame - cached[0] < PLACE_SITES_TTL_FRAMES:
            return cached[1], cached[2]
        try:
            sites = self._query_sites(observation, factory, pool)
            note = "" if sites else "引擎未返回任何合法格"
        except Exception as error:
            # 查不到不是读局势的失败：报一句说明，任务照旧跑。
            # 失败同样被缓存一个 TTL——否则引擎持续出错时会每拍重试一次。
            # 兜底面放宽到 `Exception`：这里一冒泡，整个 `status` 就不可用，而模型
            # 恰恰是在「有建筑待放置」时最需要它（实测被 `int(House)` 整死过）。
            # 出错这件事本身仍然报出来，不是静默吞掉。
            sites, note = (), f"查询失败（{error}）"
        self._sites_cache[pointer] = (frame, sites, note)
        return sites, note

    def _buildable(self, observation) -> tuple:
        """「现在能造什么、还缺什么」，每类一行。读不到目录时给空。

        引擎只在真下单之后才回 `unbuildable object_type {…}`，既不说是缺前提还是
        缺钱、也不说缺哪一条；而前提链完全由规则决定，本地就能算。这一段让模型
        在发单之前就把顺序排对（实测两个测试员都为「先造矿厂还是兵营」白花过 call）。
        """
        catalogue = (getattr(observation, "catalogue", None)
                     or getattr(self.observer, "catalogue", None))
        state = observation.state
        types = getattr(self.observer, "types", None)
        if catalogue is None or state is None or not len(catalogue):
            return ()
        owned = owned_building_ids(state, types, catalogue)
        house = observation.house
        faction = getattr(house, "faction", "") if house is not None else ""
        money = house.money if house is not None else None
        tech = state.tech_level or None
        # 两条不在 `Prerequisite` 里、引擎却会卡的门：要不要偷到某方科技、基地旁
        # 有没有水面（临水建筑）。实测「标 ✓ 却被 unbuildable 拒」正是这两条。
        stolen = stolen_labels(house)
        water_near = water_nearby(getattr(self.observer, "map_data", None),
                                  own_building_cells(state))
        lines = []
        for is_building, label, limit in ((True, "建筑", MAX_BUILDABLE_BUILDINGS),
                                          (False, "单位", MAX_BUILDABLE_UNITS)):
            found = catalogue.candidates(owned, money=money, tech=tech,
                                         faction=faction, buildings=is_building,
                                         limit=limit, stolen=stolen,
                                         water_near=water_near)
            if not found:
                continue
            parts = []
            for entry, missing in found:
                text = f"{'✓' if not missing else '✗'} {entry.id} {entry.cost}"
                if missing:
                    text += " 缺 " + "、".join(missing)
                if money is not None and entry.cost > money:
                    text += "（钱不够）"
                parts.append(text)
            lines.append(f"- {label}：" + "｜".join(parts))
        return tuple(lines)

    def _forget_sites(self) -> None:
        """手上没有待放置建筑时丢掉缓存。"""
        self._sites_cache.clear()

    def _query_sites(self, observation, factory, pool) -> tuple:
        """问引擎：基地周围哪些格可以放下这栋建筑。

        候选格由己方建筑的中心向外铺开——`PlaceQuery` 收的是候选**输入**，只
        返回其中合法的子集，故候选给得越密越好，上限由常量兜住。
        """
        state = observation.state
        types = getattr(self.observer, "types", None)
        client = getattr(self.observer, "client", None)
        building = state.object(factory.object)
        if types is None or building is None or client is None:
            # 没有连接或类型表时问不了引擎；报一句说明，读局势本身不失败
            return ()
        entry = types.info(building)
        if entry is None:
            return ()
        centers = [obj.coordinates.cell for obj in pool.buildings()] \
            or [building.coordinates.cell]
        map_data = getattr(self.observer, "map_data", None)
        candidates = place_candidates(centers, map_data, radius=PLACE_SITE_RADIUS,
                                      limit=PLACE_QUERY_MAX_LENGTH)
        found = client.place_query(
            entry, state.player_house(), candidates)
        return tuple(coord.cell for coord in found[:MAX_LISTED_SITES])

    # ------------------------------------------------------------ 自动触发
    def auto(self, observation):
        """由技法层每拍调用：跑该跑的技法。返回本拍记录。

        事件游标与模型看到的那个分开——自动层读过不代表模型看过了，反过来也一样。
        """
        events, self._auto_cursor = observation_events(self.observer, self._auto_cursor)
        records = self.autopilot.run(observation, events, self._pool(observation))
        return records

    def auto_records(self, since):
        """`since` 之后**值得一提**的自动执行记录，返回 `(记录, 新游标)`。

        空转（技法自己判断此刻无事可做）与没触发的不报——自动层多数时候就该是
        安静的，报出来只会淹掉真有事的那几条。游标仍按全部记录走。
        """
        records = self.autopilot.records
        notable = tuple(r for r in records[since:] if is_notable(r))
        return notable, len(records)

    def wake_records(self, since):
        """`since` 之后**没送出去**的唤醒，返回 `(记录, 新游标)`。

        送成功的**不报**——那条消息本身就是通知，再在 `status` 里说一遍是重复。
        失败、被限流、没送出去的才要报，否则会静默丢事件。
        """
        records = self.layer.wake.records
        missed = tuple(r for r in records[since:] if not r.get("sent"))
        return missed, len(records)

    def _match_info(self, observation):
        """本局信息：`(每拍一行, 首次的详细简报)`。

        简报只报一次，与「新结果只报一次」同理——它是静态的。地图与参战方则每拍
        都带：模型每次读局势都该看到自己在什么局里，而上下文压缩会把早先那次吃掉。
        """
        if observation.state is None:
            return "", ""
        houses = describe_houses(observation.state)
        if not houses:                 # 还没进对局，参战方都数不出来
            return "", ""
        map_text = describe_map(self.observer.map_data)
        body = f"{map_text}｜{houses}" if map_text else houses
        line = f"本局｜{body}"
        if self._briefed:
            return line, ""
        self._briefed = True
        lines = [line]
        if observation.state.tech_level:
            lines.append(f"你的科技等级 {observation.state.tech_level}")
        return line, "\n".join(lines)

    def _own_units(self, observation) -> tuple:
        """己方单位清单，含它是否已被某条任务占用。"""
        return self._listing(observation.own, observation)

    def _enemy_units(self, observation) -> tuple:
        """可见敌方清单。"""
        return self._listing(observation.visible_enemies, observation)

    def _listing(self, objects, observation) -> tuple:
        """把对象列成「id、名字、格、在管」四件事。"""
        busy = {}
        for item in self.layer.progress():
            for agent in item["units"]:
                busy[agent] = item["tactic"]
        out = []
        for obj in objects:
            if obj.in_limbo:
                continue
            agent = self.observer.identity.agent_id(obj.pointer)
            if agent is None:
                continue
            out.append({"id": agent, "name": self._name(obj),
                        "cell": obj.coordinates.cell,
                        "tactic": busy.get(agent, "")})
        return tuple(out)

    def _name(self, obj) -> str:
        """对象类型名；没有类型表时给问号。"""
        types = getattr(self.observer, "types", None)
        return types.name(obj, "?") if types is not None else "?"

    # ------------------------------------------------------------ 工具二：卡片
    def tactics(self, query=None, observation=None) -> tuple:
        """读卡片：此刻用得上的技法。`query` 按名字与说明做子串筛选。"""
        observation = observation if observation is not None else self.observer.poll()
        pool = self._pool(observation)
        cards = self.registry.cards(Mode.MATCH, observation, pool)
        if query:
            needle = query.lower()
            cards = [c for c in cards
                     if needle in c.name.lower() or needle in c.summary.lower()]
        return tuple(cards)

    # ------------------------------------------------------------ 工具三：下达
    def call(self, requests, observation=None) -> tuple:
        """下达一到多条任务，立刻返回，不等待生效。

        每条独立受理，允许部分成功；成功与否由后面的 `status` 报。
        """
        observation = observation if observation is not None else self.observer.poll()
        return tuple(self._accept(request, observation) for request in requests)

    # ------------------------------------------------------------ 工具四：撤销
    def cancel(self, intent_ids) -> tuple:
        """撤销在管任务，交还它占用的单位。

        id 收两种写法：`status` 打印的整串（`技法名#hash`）与裸 hash。打印给人看的
        那一串照抄回来必须能用——实测只认裸 hash，模型照抄必失败，而这句话本身
        还长得像「任务已结束」，很难看出是格式问题。
        """
        out = []
        for intent_id in intent_ids:
            ok = self.layer.cancel(str(intent_id).split("#")[-1])
            out.append({"intent_id": intent_id, "cancelled": ok,
                        "note": "" if ok else UNKNOWN_INTENT})
        return tuple(out)

    @staticmethod
    def render_cancels(results) -> str:
        """撤销结果的一行文本。"""
        return "\n".join(
            f"{'已撤销' if item['cancelled'] else '未撤销'} {item['intent_id']}"
            + (f"：{item['note']}" if item["note"] else "")
            for item in results)

    # ------------------------------------------------------------ 内部
    def _accept(self, request: CallRequest, observation) -> CallResult:
        """受理一条请求；任一项校验不过就整条拒绝，并说明原因。"""
        try:
            tactic = self.registry.get(request.tactic)
            info = tactic.info
            if not info.expose:
                return CallResult(False, request.tactic,
                                  error="这是零件，只供组合技法调用")
            if not self.registry.policy.allows(info):
                return CallResult(False, request.tactic,
                                  error=f"等级 {info.level} 超出门槛，或已被停用")
            # 参数先校验：它比条件更具体（「缺少参数 type」胜过「此刻用不上：can_afford」），
            # 且补好默认值后，参数型条件才能拿到完整参数。
            params = self.registry.check_params(request.tactic, request.params)
            # 顺序仍是「先条件、后单位」：单位名单全死光时那句真话不该被条件名挡掉
            missing = self.registry.missing_conditions(info, observation,
                                                       self._pool(observation),
                                                       params)
            if missing:
                return CallResult(False, request.tactic,
                                  error=f"此刻用不上：{explain(missing)}")
        except TacticError as error:
            return CallResult(False, request.tactic, error=str(error))

        units, problem = self._check_units(request.units, observation,
                                           request.tactic)
        if problem:
            return CallResult(False, request.tactic, error=problem)
        taken = self._taken(units)
        if taken:
            # 说清「谁忙、谁还空着」：模型据此重新分配（改点空闲的那几个，或先撤销
            # 再改派），而不是只看到一句「被拒了」就整条放弃。
            free = [unit for unit in units if unit not in taken]
            if free:
                hint = (f"空闲可用的还有 {list(free)}——可以只点它们重新下单，"
                        f"或先撤销再改派")
            elif request.tactic in HOUSE_LEVEL:
                hint = ("这个厂正忙；生产与放置一次只能排一条，等这条结算"
                        "（下一次 `status` 会报结果）再排下一条")
            else:
                hint = "点名的单位都在忙；先撤销再改派，或换别的单位"
            return CallResult(False, request.tactic,
                              error=f"这些单位已在其它任务里：{list(taken)}。{hint}")

        call = TacticCall(tactic=request.tactic, params=params,
                          scope=Scope(objects=units), issuer="model",
                          created_frame=observation.frame,
                          ttl_frames=request.ttl_frames)
        try:
            squad = self.layer.assign(call, observation)
        except TacticError as error:
            return CallResult(False, request.tactic, error=str(error))
        if self.log is not None:
            self.log.record(observation.frame, "command_accepted", intent=call,
                            detail={"tactic": call.tactic, "units": list(units),
                                    "params": params})
        return CallResult(True, request.tactic, intent_id=squad.intent.id)

    def _check_units(self, units, observation, tactic=""):
        """单位必须存在、且属于己方，否则当场拒绝。

        房子级动作（造楼、造兵、放置）也要点名一个己方单位——任务得挂在谁头上、
        命令生效的判据也记在它身上。模型最容易漏的就是这一步，故**把该点谁直接
        写进拒因**，别让它靠猜（实测两个玩家都为这白烧过一步）。
        """
        if not units:
            what = HOUSE_LEVEL.get(tactic)
            if what:
                return (), (f"没有给出单位——{tactic} 虽然是房子级动作，任务仍要挂在"
                            f"某个己方单位上：把{what}的 id 放进 units"
                            f"（`status` 的己方单位段里有）")
            return (), "没有给出单位"
        own = self._pool(observation)
        unknown = [u for u in units if own.object_of(u) is None]
        if unknown:
            return (), f"这些 id 不是你方可用单位：{unknown}"
        return tuple(units), ""

    def _taken(self, units) -> tuple:
        """已被别的任务占住的单位。同一时刻一个单位只归一条任务。"""
        busy = set()
        for item in self.layer.progress():
            busy.update(item["units"])
        return tuple(u for u in units if u in busy)

    def _pool(self, observation) -> UnitPool:
        """给适用条件用的临时 subject。"""
        return UnitPool(observation, self.observer.identity)
