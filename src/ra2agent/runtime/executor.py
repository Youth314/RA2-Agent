"""L0 执行器：把意图翻译成引擎命令，并验证其生效。

设计见 `.agents/notes/设计/架构设计.md#l1-与-l0-的边界`。L0 从不选择：同一意图在任何
局面下走同一条命令，只有校验不过才拒绝。

## 命令选路

| 意图 | 命令 | 动作 | 理由 |
|---|---|---|---|
| `MoveTo{stance=aggressive}` | `UnitOrder` | `ATTACK_MOVE` | 移动并迎击 |
| `MoveTo{stance=passive}` | `UnitOrder` | `MOVE` | 只移动 |
| `MoveTo{stance=hold}` | `UnitOrder` | `STOP` | 原地驻守 |
| `Hold` | `UnitOrder` | `STOP` | 同上 |
| `Attack` | `UnitOrder` | `ATTACK` | 任务类动作 |
| `Sell` | `ClickEvent` | `Sell` | 刚放置的建筑处于 `Mission_Construction`，`UnitOrder` 会拒绝 |
| `Deploy` | `ClickEvent` | `Deploy` | 同上 |
| `Produce` | `ProduceOrder` | — | 只需类型条目 |
| `Place` | `PlaceBuilding` | — | 只需对象指针与坐标 |

任务类动作一律走 `UnitOrder`，不用 `MissionClicked`：后者无条件传格子，比前者
多一条崩溃路径。依据见 `.agents/notes/引擎/命令能力测绘结果.md`。

## 生效验证

排队命令要等主循环执行，实测约 4 帧。发送成功不等于生效：`UnitOrder` 丢弃引擎
内部的返回值，引擎拒绝时静默。因此每条命令都配一条状态谓词，等谓词成立才返回观测匹配；
帧数用尽报 `Timeout`，帧不推进报 `GameNotResponding`。

判据的实测与推断之别：`STOP` 看 `mission`、`MOVE` 看 `destination` 有实测依据；
`ATTACK`、`Sell`、`Deploy`、`Produce`、`Place` 的判据为推断，待联机验证。

## 边界

- 意图的 `scope`（对象租约）由 L1 及以上仲裁，L0 只做引擎安全所需的归属校验。
- 生命周期状态由 L1 更新：L0 的回执只指状态谓词匹配，不证明本次命令造成变化——
  移动意图的达成是「到位」，由 L1 判定。
- 执行器不改写意图，也不重发；重复下发由 L1 的循环决定。

## 决策日志事件

`command_rejected`、`command_sent`、`command_failed`、`command_unverified`、
`command_executed`。
"""
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable

from ..engine.client import CommandResult
from ..constants import (LoadStage, Mission, NetworkEvent, PLACE_QUERY_MAX_LENGTH,
                        PLACE_SITE_RADIUS, UnitAction)
from ..errors import (CommandFailed, GameNotResponding, InvalidCommand,
                      ProtocolError, Timeout)
from .formation import place_candidates
from .intents import (Attack, Deploy, Hold, Intent, MoveTo, Place, Produce, Sell,
                      Stance)
from ..engine.state import Coordinates, GameState, ObjectType, cell_center
from ..engine.validate import Validator

#: 命令生效的默认帧数上限。实测移动 4 帧、生产 14 帧、部署 17 帧，故留出余量。
DEFAULT_MAX_WAIT_FRAMES = 45

#: 服务端 `error_message` 到稳定原因码的映射。
#: 原文措辞不一，故按子串匹配；未命中的归入 `unknown`，原文随异常保留。
#: `no_completed_object` 来自 `PlaceBuilding` 的实测原文（该建筑已不在任何工厂的
#: 完工条目里），此前被归成 `unknown`，模型看不出是「手上没有可放的建筑」。
ERROR_REASONS = (
    ("object not found", "object_missing"),
    ("illegal mission", "illegal_mission"),
    ("invalid unit action", "action_unimplemented"),
    ("invalid house", "invalid_house"),
    ("proximity check failed", "placement_blocked"),
    ("not found from any factory", "no_completed_object"),
    ("unbuildable", "unbuildable"),
    ("invalid id", "invalid_type_id"),
)


def reason_for(message) -> str:
    """把服务端错误原文归一化为原因码。"""
    text = (message or "").lower()
    for needle, reason in ERROR_REASONS:
        if needle in text:
            return reason
    return "unknown"


# ---------------------------------------------------------------- 生效判据
def _every(pointers, predicate) -> Callable[[GameState], bool]:
    """每个对象都存在且满足条件。"""
    def check(state):
        for pointer in pointers:
            found = state.object(pointer)
            if found is None or not predicate(found):
                return False
        return True
    return check


def _transformed(pointers) -> Callable[[GameState], bool]:
    """对象指针已消失或已标记部署。

    基地车部署会销毁原对象、另建一个建筑对象，故以旧指针消失为主要信号。
    """
    def check(state):
        for pointer in pointers:
            found = state.object(pointer)
            if found is not None and not found.deployed:
                return False
        return True
    return check


def _selling_or_gone(pointers) -> Callable[[GameState], bool]:
    """对象已进入变卖或已消失。"""
    def check(state):
        for pointer in pointers:
            found = state.object(pointer)
            if found is not None and found.mission != Mission.SELLING:
                return False
        return True
    return check


def _placed(pointer, cell) -> Callable[[GameState], bool]:
    """建筑已落位到指定格。"""
    def check(state):
        found = state.object(pointer)
        return (found is not None and found.on_map and not found.in_limbo
                and found.coordinates.cell == cell)
    return check


def _factory_snapshot(state: GameState) -> tuple:
    """己方生产队列的可比较快照。

    引擎不回报队列内容与类型的对应关系（`Factory.queued_objects` 是对象指针），
    故只能说「队列状态变了」，不能说「该类进了队列」。
    """
    return tuple(sorted((f.progress_timer, f.queued_objects, f.on_hold, f.completed)
                        for f in state.own_factories()))


def _move_action(stance, cell):
    """按姿态选移动动作，返回 `(action, coordinates)`。"""
    if stance == Stance.HOLD:
        return UnitAction.STOP, None
    if stance == Stance.AGGRESSIVE:
        return UnitAction.ATTACK_MOVE, cell_center(*cell)
    if stance == Stance.PASSIVE:
        return UnitAction.MOVE, cell_center(*cell)
    raise InvalidCommand(f"未知 stance {stance!r}")


# ---------------------------------------------------------------- 命令计划
@dataclass(frozen=True)
class CommandPlan:
    """一条意图翻译出的命令及其生效判据。

    不含字节：载荷由 `Client` 按其接口构造，`Executor._deliver` 只按 `command`
    分派。故 `Executor.plan` 可在无连接的情况下测选路。

    `verify` 无默认值：忘给判据就等于把「已发出」当「已生效」，而
    `UnitOrder` 的失败恰恰是静默的。
    """

    kind: str
    command: str
    action: UnitAction | NetworkEvent | None
    verify: Callable[[GameState], bool]
    pointers: tuple[int, ...] = ()
    target: int | None = None
    coordinates: Coordinates | None = None
    object_type: ObjectType | None = None
    facts: dict = field(default_factory=dict)

    @property
    def action_name(self) -> str:
        """动作名，用于日志与报错。"""
        if self.action is None:
            return "-"
        return self.action.name if isinstance(self.action, IntEnum) else str(self.action)

    def describe(self) -> str:
        """一行描述，用于日志与报错。"""
        parts = [self.command, self.action_name]
        if self.pointers:
            parts.append("对象=" + ",".join(str(p) for p in self.pointers))
        if self.target:
            parts.append(f"目标={self.target}")
        if self.coordinates is not None:
            parts.append(f"格={self.coordinates.cell}")
        if self.object_type is not None:
            parts.append(f"类型={self.object_type.name}")
        return " ".join(parts)


@dataclass(frozen=True)
class ExecutionOutcome:
    """一次已提交且观测判据匹配的执行；不表示任务完成。

    `state` 是判据成立时的那一帧。执行期间驱动了若干帧，调用方应把它交给
    `Observer.absorb`；若 `read_state` 已包装 `Observer.poll`，则不必。
    """

    intent_id: str
    kind: str
    plan: CommandPlan
    frames_waited: int
    polls: int
    state: GameState
    result: CommandResult
    receipt: str = "observed_match"
    evidence: str = "state_changed"
    submitted_frame: int | None = None

    def describe(self) -> str:
        """一行摘要，用于日志与人工检查。"""
        return (f"{self.kind}#{self.intent_id} {self.plan.describe()}｜"
                f"等 {self.frames_waited} 帧、{self.polls} 次观测｜"
                f"帧 {self.state.frame}｜{self.receipt}/{self.evidence}")


# ---------------------------------------------------------------- 执行器
class Executor:
    """把意图翻译为引擎命令并验证生效。无策略，不含选择。"""

    #: 意图 `kind` 到选路方法的映射。
    _ROUTES = {
        "move_to": "_plan_move",
        "attack": "_plan_attack",
        "hold": "_plan_hold",
        "deploy": "_plan_deploy",
        "produce": "_plan_produce",
        "place": "_plan_place",
        "sell": "_plan_sell",
    }

    def __init__(self, client, identity, types=None, validator=None, log=None, *,
                 max_wait_frames=DEFAULT_MAX_WAIT_FRAMES, poll_interval=0.05,
                 timeout_s=10.0,
                 focus_window=1.5, read_state=None, sleep=time.sleep,
                 clock=time.monotonic):
        """构造执行器。

        `identity` 把意图里的 Agent 侧 id 解析为引擎指针；`validator` 应带地图，
        否则坐标类意图一律被拒。`read_state` 默认读 `client.get_state`；传入包装
        `Observer.poll` 的读取函数可在等待期间同步维护迷雾与标识。`max_wait_frames`
        是命令生效的帧数上限，取值依据见 `DEFAULT_MAX_WAIT_FRAMES`。
        """
        self.client = client
        self.identity = identity
        self.types = types
        self.validator = validator or Validator()
        self.log = log
        self.max_wait_frames = max_wait_frames
        self.poll_interval = poll_interval
        self.timeout_s = timeout_s
        self.focus_window = focus_window
        self._read = read_state or client.get_state
        self._sleep = sleep
        self._clock = clock

    # ------------------------------------------------------------ 对外
    def plan(self, intent, state) -> CommandPlan:
        """选路并完成发送前校验；不发送任何命令，不做 I/O。

        抛 `InvalidCommand` 表示意图在本地被拒，游戏未受影响。
        """
        if not isinstance(intent, Intent):
            raise InvalidCommand(f"不是意图对象：{type(intent).__name__}")
        route = self._ROUTES.get(intent.kind)
        if route is None:
            raise InvalidCommand(f"L0 不认识意图类型 {intent.kind!r}")
        if not isinstance(state, GameState):
            raise InvalidCommand("需要一帧 GameState 才能翻译意图")
        if intent.is_terminal():
            raise InvalidCommand(f"意图已处于终态 {intent.state}，不再执行")
        if intent.is_expired(state.frame):
            raise InvalidCommand(
                f"意图已过期：帧 {state.frame} ≥ 到期帧 {intent.expires_at()}")
        return getattr(self, route)(intent, state)

    def execute(self, intent, state) -> ExecutionOutcome:
        """翻译、发送并等待生效。

        返回时判据已成立。失败按类型抛异常：本地拒绝 `InvalidCommand`、服务端
        拒绝 `CommandFailed`、帧不推进 `GameNotResponding`、判据未成立 `Timeout`。
        后两者表示命令已发出但结果未知。
        """
        try:
            latest = self._read()
            self._check_context(state, latest)
            self.identity.update(latest)
            state = latest
            plan = self.plan(intent, state)
        except InvalidCommand as error:
            self._record(state.frame, "command_rejected", intent, {"error": str(error)})
            raise
        preexisting = plan.verify(state)
        try:
            result = self._deliver(plan)
        except (GameNotResponding, Timeout) as error:
            self._unverified(error, intent, plan, state, None)
            raise
        self._record(state.frame, "command_sent", intent, plan.facts)
        if not result.ok:
            reason = reason_for(result.error)
            error = CommandFailed(
                f"{plan.describe()} 被服务端拒绝："
                f"{result.error or f'code={result.code}'}",
                command_type=plan.command, reason=reason)
            self._record(state.frame, "command_failed", intent,
                         {"command": plan.describe(), "reason": reason,
                          "error": str(error)})
            raise error
        try:
            final, frames, polls = self._await(plan, state)
        except (GameNotResponding, Timeout) as error:
            self._unverified(error, intent, plan, state, result)
            raise
        outcome = ExecutionOutcome(intent_id=intent.id, kind=intent.kind, plan=plan,
                                   frames_waited=frames, polls=polls, state=final,
                                   result=result,
                                   evidence=("preexisting_match" if preexisting
                                             else "state_changed"),
                                   submitted_frame=state.frame)
        self._record(final.frame, "command_executed", intent,
                     {"command": plan.describe(), "frames_waited": frames,
                      "polls": polls, "receipt": outcome.receipt,
                      "evidence": outcome.evidence})
        return outcome

    def _unverified(self, error, intent, plan, state, result):
        """保留尝试依据供 L1 回读，不能据异常自动重复提交。"""
        error.plan = plan
        error.intent = intent
        error.submitted_frame = state.frame
        error.result = result
        self._record(state.frame, "command_unverified", intent,
                     {"command": plan.describe(), "error": str(error),
                      "submission": "acknowledged" if result is not None else "unknown"})

    @staticmethod
    def _check_context(baseline, current):
        """跨局次、席位变化或帧回退时不使用旧意图。"""
        try:
            before, after = baseline.player_house(), current.player_house()
        except ProtocolError as error:
            raise InvalidCommand(str(error)) from error
        if (current.stage != LoadStage.INGAME
                or current.frame < baseline.frame
                or (before.pointer, before.array_index) !=
                   (after.pointer, after.array_index)
                or after.defeated or after.is_winner or after.is_loser):
            raise InvalidCommand("对局或玩家上下文已变化，拒绝旧意图")

    # ------------------------------------------------------------ 发送
    def _deliver(self, plan) -> CommandResult:
        """按选路结果调用客户端方法。"""
        if plan.command == "UnitOrder":
            return self.client.unit_order(plan.pointers, plan.action,
                                          target_object=plan.target,
                                          coordinates=plan.coordinates)
        if plan.command == "ClickEvent":
            return self.client.click_event(plan.pointers, plan.action)
        if plan.command == "ProduceOrder":
            return self.client.produce_order(plan.object_type)
        if plan.command == "PlaceBuilding":
            return self.client.place_building(plan.pointers[0], plan.coordinates)
        raise InvalidCommand(f"未知命令类型 {plan.command!r}")

    # ------------------------------------------------------------ 等待生效
    def _await(self, plan, submitted) -> tuple[GameState, int, int]:
        """等判据成立，返回 `(状态, 等待帧数, 观测次数)`。

        帧数从发送后的第一次观测算起：调用方给的那一帧可能已经陈旧（L1 按
        1–5 Hz 运行，一拍就是几十帧），拿它当基线会把预算白白耗尽。
        """
        state = self._read()
        start = last = state.frame
        changed_at = self._clock()
        deadline = changed_at + self.timeout_s
        polls = 1
        while True:
            if state.frame < last:
                raise GameNotResponding("命令已提交，但观测帧回退；结果未知")
            try:
                self._check_context(submitted, state)
            except InvalidCommand as error:
                raise GameNotResponding(
                    "命令已提交，但对局上下文变化；结果未知") from error
            if plan.verify(state):
                return state, state.frame - start, polls
            waited = state.frame - start
            if waited >= self.max_wait_frames:
                raise Timeout(f"{plan.describe()} 已等 {waited} 帧，"
                              f"超过 {self.max_wait_frames} 帧仍未见状态变化")
            if state.frame != last:
                last = state.frame
                changed_at = self._clock()
            elif self._clock() - changed_at >= self.focus_window:
                # 帧停了足够久才值得花一次窗口探测；正常推进时每帧都会重置计时
                if not self._advancing(self.focus_window):
                    raise GameNotResponding(
                        f"{plan.describe()} 已发出，但帧停在 {state.frame} 不再推进，"
                        f"窗口可能失焦；命令是否生效未知")
                changed_at = self._clock()
            if self._clock() >= deadline:
                raise Timeout(f"{plan.describe()} 已等 {waited} 帧、"
                              f"{self.timeout_s} 秒仍未见状态变化")
            self._sleep(self.poll_interval)
            polls += 1
            state = self._read()

    def _advancing(self, window) -> bool:
        """游戏主循环是否在推进。

        判据同 `Client.is_advancing`，但经 `read_state` 读帧，使失焦探测期间的
        `cells_difference` 增量也并入观测层。
        """
        before = self._read()
        self._sleep(window)
        return self._read().frame - before.frame >= 1

    # ------------------------------------------------------------ 选路
    def _plan_move(self, intent, state) -> CommandPlan:
        pointers = self._pointers(intent.units)
        action, coordinates = _move_action(intent.stance, intent.cell)
        self.validator.check_unit_order(state, pointers, action,
                                        coordinates=coordinates)
        if action == UnitAction.STOP:
            verify = _every(pointers, lambda obj: obj.mission == Mission.STOP)
        else:
            cell = tuple(intent.cell)
            verify = _every(pointers, lambda obj: obj.destination.cell == cell)
        return CommandPlan(kind=intent.kind, command="UnitOrder", action=action,
                           pointers=pointers, coordinates=coordinates,
                           facts=self._facts(state, pointers), verify=verify)

    def _plan_attack(self, intent, state) -> CommandPlan:
        pointers = self._pointers(intent.units)
        target = self._pointer(intent.target, state)
        self.validator.check_unit_order(state, pointers, UnitAction.ATTACK,
                                        target_object=target)
        return CommandPlan(
            kind=intent.kind, command="UnitOrder", action=UnitAction.ATTACK,
            pointers=pointers, target=target, facts=self._facts(state, pointers),
            verify=_every(pointers, lambda obj: obj.mission == Mission.ATTACK))

    def _plan_hold(self, intent, state) -> CommandPlan:
        pointers = self._pointers(intent.units)
        self.validator.check_unit_order(state, pointers, UnitAction.STOP)
        return CommandPlan(
            kind=intent.kind, command="UnitOrder", action=UnitAction.STOP,
            pointers=pointers, facts=self._facts(state, pointers),
            verify=_every(pointers, lambda obj: obj.mission == Mission.STOP))

    def _plan_deploy(self, intent, state) -> CommandPlan:
        pointers = self._pointers(intent.units)
        self.validator.check_click_event(state, pointers)
        return CommandPlan(kind=intent.kind, command="ClickEvent",
                           action=NetworkEvent.DEPLOY, pointers=pointers,
                           facts=self._facts(state, pointers),
                           verify=_transformed(pointers))

    def _plan_sell(self, intent, state) -> CommandPlan:
        pointers = self._pointers(intent.buildings)
        self.validator.check_click_event(state, pointers)
        return CommandPlan(kind=intent.kind, command="ClickEvent",
                           action=NetworkEvent.SELL, pointers=pointers,
                           facts=self._facts(state, pointers),
                           verify=_selling_or_gone(pointers))

    def _plan_produce(self, intent, state) -> CommandPlan:
        entry = self._object_type(intent)
        baseline = _factory_snapshot(state)
        return CommandPlan(
            kind=intent.kind, command="ProduceOrder", action=None,
            object_type=entry, facts={"type": entry.name, "frame": state.frame},
            verify=lambda current: _factory_snapshot(current) != baseline)

    def _plan_place(self, intent, state) -> CommandPlan:
        building = self._pointer(intent.building, state)
        cell = intent.cell
        if cell is None:
            cell = self._nearest_place_cell(building, state)
            if cell is None:
                raise InvalidCommand(
                    "引擎没给出任何合法落点，这栋建筑暂时放不下")
        coordinates = cell_center(*cell)
        self.validator.check_place(coordinates)
        cell = tuple(cell)
        return CommandPlan(
            kind=intent.kind, command="PlaceBuilding", action=None,
            pointers=(building,), coordinates=coordinates,
            facts=self._facts(state, (building,)), verify=_placed(building, cell))

    def _nearest_place_cell(self, building, state):
        """替模型问引擎要一格合法落点：最近的优先，问不到给 `None`。

        合法性只有引擎说了算，故这里拿己方建筑当中心由近及远铺候选，交给
        `PlaceQuery` 筛——它返回的第一格就是离基地最近的合法格。这一步是 I/O，
        所以归 L0：技法层不许问引擎。
        """
        if self.types is None or state is None:
            return None
        obj = state.object(building)
        if obj is None:
            return None
        entry = self.types.info(obj)
        if entry is None:
            return None
        centers = [o.coordinates.cell for o in state.own_objects() if o.is_building] \
            or [obj.coordinates.cell]
        map_data = getattr(self.validator, "map_data", None)
        candidates = place_candidates(centers, map_data, radius=PLACE_SITE_RADIUS,
                                     limit=PLACE_QUERY_MAX_LENGTH)
        found = self.client.place_query(entry, state.player_house(), candidates)
        return tuple(found[0].cell) if found else None

    # ------------------------------------------------------------ 解析与日志
    def _pointers(self, agent_ids) -> tuple[int, ...]:
        """把意图里的 Agent 侧 id 批量解析为引擎指针。"""
        if not agent_ids:
            raise InvalidCommand("意图未给出任何对象")
        return tuple(self._pointer(agent) for agent in agent_ids)

    def _pointer(self, agent_id, state=None) -> int:
        """解析单个 Agent 侧 id；未知或不在当前状态中即拒绝。"""
        pointer = self.identity.pointer_of(agent_id)
        if pointer is None:
            raise InvalidCommand(f"对象 id {agent_id} 不在标识表中：尚未观测到或已消失")
        if state is not None and state.object(pointer) is None:
            raise InvalidCommand(f"对象 id {agent_id}（指针 {pointer}）不在当前状态中")
        return pointer

    def _object_type(self, intent) -> ObjectType:
        """按类型指针查类型表。"""
        if self.types is None:
            raise InvalidCommand("尚未取得类型表，无法翻译 Produce")
        entry = self.types.info(intent.type_pointer)
        if entry is None:
            raise InvalidCommand(
                f"类型指针 {intent.type_pointer} 不在类型表中"
                f"（{intent.type_name or '未给名字'}）")
        return entry

    @staticmethod
    def _facts(state, pointers) -> dict:
        """决策依据的事实摘要：各对象当前所在的格。"""
        cells = {}
        for pointer in pointers:
            found = state.object(pointer)
            if found is not None:
                cells[str(pointer)] = list(found.coordinates.cell)
        return {"objects": cells, "frame": state.frame}

    def _record(self, frame, event, intent, detail) -> None:
        """写决策日志；未配置日志时不做任何事。"""
        if self.log is None:
            return
        self.log.record(frame, event, intent=intent, detail=detail)
