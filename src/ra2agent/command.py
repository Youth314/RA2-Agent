"""指挥层：模型与技法层之间的那道门。

模型只看见四件事——读局势、读卡片、下达、撤销。**工具数固定，能力数随技法库
增长**：库里可以有几百条技法，模型看到的永远只是这四扇门，门里的东西写在卡片上。

本模块不含策略，也不碰引擎：它把技法层的能力包成稳定的调用面，MCP 服务与假模型
脚本都只是它的薄壳。契约见 `.agents/notes/指挥层.md`。

受理请求时先做一遍技法层同样的校验（参数、等级、适用条件、单位归属），使模型当场
拿到「这条用不上、参数不对」，而不是等一拍之后静默失败。
"""
from dataclasses import dataclass, field

from .errors import TacticError
from .intents import Scope, TacticCall
from .tactics import Mode

#: 撤销不了的返回文案。
UNKNOWN_INTENT = "没有这条在管任务：可能已结束或被撤销"


#: 一次最多列多少个单位，免得文本长到把上下文吃掉。
MAX_LISTED_UNITS = 24


def _unit_line(item) -> str:
    """一个单位一行：id、名字、格，以及它是不是已经在某条任务里。"""
    state = f"在管 {item['tactic']}" if item.get("tactic") else "空闲"
    return f"- {item['id']}｜{item['name']}｜格 ({item['cell'][0]},{item['cell'][1]})｜{state}"


class UnitPool:
    """适用条件用的一队单位视图：此刻己方全部可用单位当成一队。

    `tactics` 与 `call` 在还没建编队时也要评适用条件，故给它一个临时 subject。
    """

    def __init__(self, observation, identity):
        self.observation = observation
        self.identity = identity
        self._own = {}
        for obj in observation.own:
            if obj.in_limbo:
                continue
            agent = identity.agent_id(obj.pointer)
            if agent is not None:
                self._own[agent] = obj
        self._pointers = {obj.pointer: agent for agent, obj in self._own.items()}

    def agents(self) -> tuple:
        """己方全部可用单位的 agent id。"""
        return tuple(self._own)

    def object_of(self, agent_id):
        """按 agent id 取对象。"""
        return self._own.get(agent_id)

    def agent_id(self, pointer):
        """引擎指针转 agent id。"""
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
    units: tuple = ()
    enemies: tuple = ()
    running: tuple = ()
    events: tuple = ()
    notices: tuple = ()

    def render(self) -> str:
        """渲染成模型读的文本，形状稳定、尽量短。"""
        lines = [f"局势｜{self.summary}"]
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
        if self.events:
            lines.append(f"新结果 {len(self.events)} 条：")
            for event in self.events:
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
        return StatusReport(frame=observation.frame, summary=observation.summary(),
                            units=self._own_units(observation),
                            enemies=self._enemy_units(observation),
                            running=self.layer.progress(), events=tuple(completed),
                            notices=tuple(notices))

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
