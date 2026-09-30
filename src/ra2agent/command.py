"""指挥层：模型与技法层之间的那道门。

模型只看见四件事——读局势、读卡片、下达、撤销。**工具数固定，能力数随技法库
增长**：库里可以有几百条技法，模型看到的永远只是这四扇门，门里的东西写在卡片上。

本模块不含策略，也不碰引擎：它把技法层的能力包成稳定的调用面，MCP 服务与假模型
脚本都只是它的薄壳。契约见 `.agents/notes/指挥层.md`。

受理请求时先做一遍技法层同样的校验（参数、等级、适用条件、单位归属），使模型当场
拿到「这条用不上、参数不对」，而不是等一拍之后静默失败。
"""
from dataclasses import dataclass, field

from .autopilot import Autopilot
from .constants import LandType, PLACE_QUERY_MAX_LENGTH
from .errors import Ra2Error, TacticError
from .events import summarize
from .intents import Scope, TacticCall
from .state import cell_center
from .tactics import Mode

#: 撤销不了的返回文案。
UNKNOWN_INTENT = "没有这条在管任务：可能已结束或被撤销"


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
    """参战各方：国家名、是不是你、人类还是电脑、出局没有。"""
    parts = []
    for house in state.houses:
        if house.is_neutral:
            continue
        who = "你" if house.current_player else ("人类" if house.is_human_player else "电脑")
        if house.defeated:
            who += "，已出局"
        parts.append(f"{house.name}（{who}）")
    return f"参战 {len(parts)} 方｜" + " · ".join(parts) if parts else ""


#: 一次最多列多少个单位，免得文本长到把上下文吃掉。
MAX_LISTED_UNITS = 24

#: 电厂一类建筑的生产步数：`progress_timer` 走到这里即完工（实测 Allied Power Plant）。
PRODUCTION_STEPS = 54

#: 一个落点集最多给模型看几个。查出来的合法格可达几十个，全给只会淹掉上下文。
MAX_LISTED_SITES = 12

#: 落点集缓存多少帧。`PlaceQuery` 是一次真机往返，不该每次读局势都查。
PLACE_SITES_TTL_FRAMES = 22

#: 候选落点相对基地中心向外的搜索半径（格）。
PLACE_SITE_RADIUS = 10


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
    """一行说清「手上有一栋待放置的建筑」。"""
    building = state.object(factory.object) if state is not None else None
    name = types.name(building, "?") if types is not None and building else "?"
    where = building.coordinates.cell if building is not None else None
    at = f"（格 {where[0]},{where[1]}）" if where else ""
    return f"- #{agent_id}｜{name}{at}｜等待放置"


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
    #: 建筑待放置但拿不到落点集时的说明；拿到了则为空。
    placement_note: str = ""
    #: 当前可选落点（格坐标）。由模型挑一个，作为 `place_ready_building` 的参数。
    sites: tuple = ()
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
            lines.append(f"待放置 {len(self.placement)} 栋：")
            lines.extend(self.placement)
            if self.sites:
                shown = "、".join(f"({x},{y})" for x, y in self.sites)
                lines.append(f"- 可选落点：{shown}")
                lines.append("- 用 call place_ready_building 指定其中一格"
                             "（参数 cell，形如 [x,y]）")
            elif self.placement_note:
                lines.append(f"- 落点未知：{self.placement_note}")
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
                lines.append(
                    f"- {event['tactic']}#{event['intent_id']}｜{event['state']}｜"
                    f"到位 {len(event['arrived'])} 损失 {len(event['lost'])} "
                    f"失败 {len(event['failed'])}")
        if self.notices:
            lines.append(f"告警 {len(self.notices)} 条：")
            for notice in self.notices:
                lines.append(f"- {notice['kind']}（帧 {notice['frame']}）"
                             f"｜{notice['detail']}")
        return "\n".join(lines)


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
        self._sites: tuple = ()
        self._sites_signature = None
        self._sites_frame: int | None = None
        self._sites_note = ""
        #: 自动触发层。技法按名片里的触发声明自己跑，产出的是脉冲。
        # 唤醒桥挂在技法层上：一个会话一份额度，自动层与模型调用的路径共用
        self.autopilot = Autopilot(layer.registry, layer.executor, log=log,
                                   wake=layer.wake)

    # ------------------------------------------------------------ 工具一：局势
    def status(self, observation=None) -> StatusReport:
        """读局势：一行摘要、在管任务、以及上次读过之后的新结果与告警。

        新结果只报一次：读走即清空，免得模型每拍都重看同一批。
        """
        observation = observation if observation is not None else self.observer.poll()
        completed = self.layer.completed[self._seen_completed:]
        notices = self.layer.notices[self._seen_notices:]
        self._seen_completed = len(self.layer.completed)
        self._seen_notices = len(self.layer.notices)
        match, brief = self._match_info(observation)
        new_events, self._seen_events = observation_events(self.observer, self._seen_events)
        auto, self._seen_auto = self.auto_records(self._seen_auto)
        wakes, self._seen_wakes = self.wake_records(self._seen_wakes)
        pool = self._pool(observation)
        placement, placement_note, sites = self._placement(observation, pool)
        return StatusReport(frame=observation.frame, summary=observation.summary(),
                            match=match, brief=brief, events=new_events, auto=auto,
                            wakes=wakes,
                            power=self._power(observation),
                            production=self._production(observation),
                            placement=placement, placement_note=placement_note,
                            sites=sites,
                            units=self._own_units(observation),
                            enemies=self._enemy_units(observation),
                            running=self.layer.progress(), results=tuple(completed),
                            notices=tuple(notices))

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
        """完工待放置的建筑，以及它当前的可选落点。

        返回 `(建筑各行, 拿不到落点时的说明, 落点元组)`。合法格只有引擎说了算，
        故这里替模型问一次 `PlaceQuery`——**结果按帧缓存**，不然每次读局势都要
        一次真机往返。模型从 `sites` 里挑一格回传，L0 照旧只负责执行。
        """
        state = observation.state
        factories = self._completed_factories(state)
        if not factories:
            self._forget_sites()
            return (), "", ()
        types = getattr(self.observer, "types", None)
        rows = []
        for factory in factories:
            agent = pool.agent_id(factory.object)
            rows.append(describe_placement(agent if agent is not None else "?",
                                           factory, state, types))
        sites, note = self._sites_for(observation, factories, pool)
        return tuple(rows), note, sites

    @staticmethod
    def _completed_factories(state):
        """已完工、等玩家放置的那些工厂条目。"""
        if state is None:
            return ()
        return tuple(factory for factory in state.own_factories() if factory.completed)

    def _sites_for(self, observation, factories, pool) -> tuple:
        """取（或复用缓存的）合法落点集。"""
        signature = tuple(factory.object for factory in factories)
        frame = observation.frame
        fresh = (self._sites_signature == signature and self._sites_frame is not None
                 and frame - self._sites_frame < PLACE_SITES_TTL_FRAMES)
        if fresh:
            return self._sites, self._sites_note
        try:
            self._sites = self._query_sites(observation, factories[0], pool)
            self._sites_note = "" if self._sites else "引擎未返回任何合法格"
        except Ra2Error as error:
            # 查不到不是读局势的失败：报一句说明，任务照旧跑。
            # 失败同样被缓存一个 TTL——否则引擎持续出错时会每拍重试一次
            self._sites = ()
            self._sites_note = f"查询失败（{error}）"
        self._sites_signature = signature
        self._sites_frame = frame
        return self._sites, self._sites_note

    def _forget_sites(self) -> None:
        """手上没有待放置建筑时丢掉缓存。"""
        self._sites = ()
        self._sites_signature = None
        self._sites_frame = None
        self._sites_note = ""

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
        candidates = []
        seen = set()
        for base_x, base_y in centers:
            # 由近及远铺开：先给引擎的候选先被返回，故最靠基地的合法格排在最前
            for radius in range(PLACE_SITE_RADIUS + 1):
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        if max(abs(dx), abs(dy)) != radius:
                            continue
                        x, y = base_x + dx, base_y + dy
                        if (x, y) in seen:
                            continue
                        if map_data is not None and not map_data.in_bounds(x, y):
                            # 坐标越界会崩游戏，故在地图外的候选一律不发出去
                            continue
                        seen.add((x, y))
                        candidates.append(cell_center(x, y))
        found = client.place_query(
            entry, state.player_house(),
            candidates[:PLACE_QUERY_MAX_LENGTH])
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
        """撤销在管任务，交还它占用的单位。"""
        out = []
        for intent_id in intent_ids:
            ok = self.layer.cancel(intent_id)
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
            missing = self.registry.missing_conditions(info, observation,
                                                       self._pool(observation))
            if missing:
                return CallResult(False, request.tactic,
                                  error=f"此刻用不上：{'、'.join(missing)}")
            params = self.registry.check_params(request.tactic, request.params)
        except TacticError as error:
            return CallResult(False, request.tactic, error=str(error))

        units, problem = self._check_units(request.units, observation)
        if problem:
            return CallResult(False, request.tactic, error=problem)
        taken = self._taken(units)
        if taken:
            return CallResult(False, request.tactic,
                              error=f"这些单位已在其它任务里：{list(taken)}；先撤销再改派")

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

    def _check_units(self, units, observation):
        """单位必须存在、且属于己方，否则当场拒绝。"""
        if not units:
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
