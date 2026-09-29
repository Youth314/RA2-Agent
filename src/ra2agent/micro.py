"""L1 运行时：按 tick 跑技法，把意图交给基础设施，并跟踪进度。

技法只回答「这一步该下什么命令」；其余全在这里：谁需要下令、命令是否生效、卡住
怎么办、任务何时算完成或失败。

按 tick 而不是逐帧跑：单帧观测 11.9 KB，逐帧轮询不值，且寻路与自动开火由引擎
负责。默认每 22 帧（约 0.5 秒）一拍。
"""
import time
from dataclasses import dataclass
from enum import StrEnum

from .errors import (CommandFailed, GameNotResponding, InvalidCommand, Timeout,
                     TacticDenied, TacticError)
from .executor import Executor
from .intents import IntentState, TacticCall
from .observation import Observation
from .tactics import Mode, TacticRegistry
from .validate import Validator

#: 每 tick 之间的默认帧数。44 fps 下约 0.5 秒。
DEFAULT_TICK_FRAMES = 22
#: 到位宽容（格）。引擎在目标格被占时会停在邻格。
DEFAULT_ARRIVE_RADIUS = 1
#: 位置多少帧不动就算卡住。
DEFAULT_STUCK_FRAMES = 90
#: 一条命令最多重试几次。
DEFAULT_MAX_RETRIES = 3


class UnitMode(StrEnum):
    """一个单位在任务中的状态。"""

    MOVING = "moving"        # 已下令，尚未到位
    ENGAGING = "engaging"    # 正在接战
    ARRIVED = "arrived"      # 已到位
    STUCK = "stuck"          # 位置长时间不动，等换路点
    LOST = "lost"            # 对象从观测里消失
    FAILED = "failed"        # 命令反复失败


#: 不再需要下令的状态。
DONE_MODES = (UnitMode.ARRIVED, UnitMode.LOST, UnitMode.FAILED)


@dataclass
class UnitProgress:
    """一个单位的进度。"""

    agent_id: int
    pointer: int
    mode: str = UnitMode.MOVING
    goal: tuple | None = None           # 当前目标格
    target: int | None = None           # 接战中的敌人 agent id
    last_cell: tuple | None = None
    last_change_frame: int = 0
    retries: int = 0


class Squad:
    """一队单位与它们的任务。技法只读这个对象。"""

    def __init__(self, intent, units, identity, origin=None):
        self.intent = intent
        self.units = list(units)
        self.identity = identity
        self.memo: dict = {}
        self.origin = origin
        self._active: tuple = tuple(unit.agent_id for unit in self.units)
        self._observation: Observation | None = None

    # -------------------------------------------------- 技法看到的视图
    def agents(self) -> tuple:
        """本次调用该管的单位（agent id）。"""
        return self._active

    def alive(self) -> tuple:
        """还活着、还没失败的单位（agent id）。"""
        return tuple(unit.agent_id for unit in self.units
                     if unit.mode not in (UnitMode.LOST, UnitMode.FAILED))

    def object_of(self, agent_id):
        """按 agent id 取当前对象；不在观测里返回 `None`。"""
        state = self._observation.state if self._observation else None
        pointer = self.identity.pointer_of(agent_id)
        return state.object(pointer) if state is not None and pointer else None

    def agent_id(self, pointer):
        """引擎指针转 agent id。"""
        return self.identity.agent_id(pointer)

    def cell_of(self, agent_id):
        """按 agent id 取当前所在格。"""
        found = self.object_of(agent_id)
        return found.coordinates.cell if found else None

    def _view(self, observation, active):
        """运行时在调用技法前设置视图。"""
        self._observation = observation
        self._active = tuple(active)

    def __repr__(self):
        return (f"Squad({self.intent.tactic}, "
                f"{[unit.agent_id for unit in self.units]})")


class MicroLayer:
    """技法层的运行时。一个实例管多条编队任务。"""

    def __init__(self, observer, registry=None, executor=None, log=None, *,
                 tick_frames=DEFAULT_TICK_FRAMES,
                 arrive_radius=DEFAULT_ARRIVE_RADIUS,
                 stuck_frames=DEFAULT_STUCK_FRAMES,
                 max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep):
        self.observer = observer
        self.registry = registry or TacticRegistry(log=log).load_builtin()
        self.log = log
        self.tick_frames = tick_frames
        self.arrive_radius = arrive_radius
        self.stuck_frames = stuck_frames
        self.max_retries = max_retries
        self._sleep = sleep
        self._squads: list = []
        self.completed: list = []
        self.last_tick_frame: int | None = None
        if executor is None:
            executor = Executor(
                observer.client, observer.identity,
                types=observer.types,
                validator=Validator(observer.map_data),
                log=log,
                read_state=lambda: observer.poll().state)
        self.executor = executor

    # ------------------------------------------------------------ 对外
    def assign(self, call: TacticCall, observation: Observation) -> Squad:
        """接收一条指挥层意图，建立编队。

        `scope` 里的对象若已不在标识表里就跳过；一个都没有则报错，不静默。
        """
        if not isinstance(call, TacticCall):
            raise TacticError(f"技法层只接受指挥层意图，收到 {type(call).__name__}")
        self.registry.get(call.tactic)
        units, missing = [], []
        for agent in call.scope.objects:
            pointer = self.observer.identity.pointer_of(agent)
            if pointer is None:
                missing.append(agent)
                continue
            units.append(UnitProgress(agent_id=agent, pointer=pointer,
                                      last_change_frame=observation.frame))
        if not units:
            raise TacticError(f"意图 {call.tactic} 没有可用对象：{list(call.scope.objects)}")
        squad = Squad(call, units, self.observer.identity)
        self._squads.append(squad)
        self._record(observation.frame, "squad_assigned", call,
                     {"tactic": call.tactic, "units": [u.agent_id for u in units],
                      "missing": missing})
        return squad

    def tick(self, observation=None) -> list:
        """走一拍：更新进度、按需调用技法、下发意图。返回本拍的执行结果。"""
        observation = observation if observation is not None else self.observer.poll()
        outcomes = []
        for squad in list(self._squads):
            self._update(squad, observation)
            if self._settle(squad, observation, outcomes):
                continue
            self._order(squad, observation, outcomes)
            # 命令失败或即刻见效（停止、部署一类）的编队同拍结算
            self._settle(squad, observation, outcomes)
        return outcomes

    def run(self, ticks=None, poll_interval=0.05):
        """按帧节流循环。`ticks` 为 `None` 时一直跑。"""
        count = 0
        while ticks is None or count < ticks:
            frame = self.observer.client.frame()
            if (self.last_tick_frame is None
                    or frame - self.last_tick_frame >= self.tick_frames):
                self.last_tick_frame = frame
                self.tick()
                count += 1
            else:
                self._sleep(poll_interval)

    def squads(self) -> tuple:
        """当前在管的编队。"""
        return tuple(self._squads)

    def cards(self, observation, squad=None):
        """此刻该给模型看的卡片。"""
        return self.registry.cards(Mode.MATCH, observation, squad)

    # ------------------------------------------------------------ 进度
    def _update(self, squad, observation) -> None:
        """按最新观测推进每个单位的状态。"""
        state = observation.state
        enemies = {self.observer.identity.agent_id(obj.pointer)
                   for obj in observation.visible_enemies}
        for unit in squad.units:
            if unit.mode in DONE_MODES:
                continue
            found = state.object(unit.pointer)
            if found is None:
                unit.mode = UnitMode.LOST
                continue
            cell = found.coordinates.cell
            if cell != unit.last_cell:
                unit.last_cell = cell
                unit.last_change_frame = observation.frame
            if unit.mode == UnitMode.ENGAGING:
                if unit.target not in enemies:
                    unit.mode = UnitMode.MOVING
                    unit.goal = None
                    unit.target = None
                continue
            if unit.goal is not None:
                if _within(cell, unit.goal, self.arrive_radius):
                    unit.mode = UnitMode.ARRIVED
                elif observation.frame - unit.last_change_frame >= self.stuck_frames:
                    # 卡住就换路点：计数加一，下拍按 attempt 换一个落点
                    unit.retries += 1
                    unit.mode = (UnitMode.FAILED if unit.retries > self.max_retries
                                 else UnitMode.STUCK)

    def _settle(self, squad, observation, outcomes) -> bool:
        """任务结束就结算并移出，返回是否已结束。"""
        if squad.intent.is_expired(observation.frame):
            squad.intent.state = IntentState.EXPIRED
            self._finish(squad, observation, outcomes, IntentState.EXPIRED)
            return True
        if any(unit.mode not in DONE_MODES for unit in squad.units):
            return False
        arrived = sum(1 for unit in squad.units if unit.mode == UnitMode.ARRIVED)
        state = IntentState.SATISFIED if arrived else IntentState.FAILED
        squad.intent.state = state
        self._finish(squad, observation, outcomes, state)
        return True

    def _finish(self, squad, observation, outcomes, state) -> None:
        """收尾：记结算、移出编队。"""
        record = {
            "intent_id": squad.intent.id,
            "tactic": squad.intent.tactic,
            "state": str(state),
            "frame": observation.frame,
            "arrived": [u.agent_id for u in squad.units if u.mode == UnitMode.ARRIVED],
            "lost": [u.agent_id for u in squad.units if u.mode == UnitMode.LOST],
            "failed": [u.agent_id for u in squad.units if u.mode == UnitMode.FAILED],
        }
        self.completed.append(record)
        self._squads.remove(squad)
        self._record(observation.frame, "squad_settled", squad.intent, record)

    # ------------------------------------------------------------ 下令
    def _order(self, squad, observation, outcomes) -> None:
        """对需要下令的单位跑一次技法。"""
        active = [unit for unit in squad.units if self._needs_orders(unit)]
        if not active:
            return
        squad._view(observation, [unit.agent_id for unit in active])
        attempt = max(unit.retries for unit in active)
        try:
            intents = self.registry.run(
                squad.intent.tactic, observation=observation, subject=squad,
                params=squad.intent.params, frame=observation.frame,
                memo=squad.memo, log=self.log, attempt=attempt)
        except TacticDenied as error:
            # 条件不满足：本拍什么都不做，等局面变化
            self._record(observation.frame, "squad_waiting", squad.intent,
                         {"tactic": squad.intent.tactic, "reason": str(error)})
            return
        except TacticError as error:
            self._fail_squad(squad, observation, outcomes, str(error))
            return
        for intent in intents:
            self._dispatch(squad, active, intent, observation, outcomes)

    def _dispatch(self, squad, active, intent, observation, outcomes) -> None:
        """下发一条意图，并按结果更新进度。"""
        try:
            outcome = self.executor.execute(intent, observation.state)
        except GameNotResponding as error:
            # 失焦不是命令失败：整拍挂起，等帧恢复
            self._record(observation.frame, "command_paused", squad.intent,
                         {"intent": intent.kind, "reason": str(error)})
            for unit in active:
                unit.goal = None
            return
        except Timeout as error:
            for unit in active:
                unit.retries += 1
                if unit.retries > self.max_retries:
                    unit.mode = UnitMode.FAILED
                else:
                    unit.goal = None
            self._record(observation.frame, "command_retry", squad.intent,
                         {"intent": intent.kind, "reason": str(error)})
            return
        except CommandFailed as error:
            if error.reason in ("object_missing", "illegal_mission"):
                for unit in active:
                    unit.mode = UnitMode.FAILED
            else:
                self._fail_squad(squad, observation, outcomes, str(error))
            return
        except InvalidCommand as error:
            self._fail_squad(squad, observation, outcomes, str(error))
            return
        outcomes.append(outcome)
        self._advance(squad, intent, outcome.state)

    def _advance(self, squad, intent, state) -> None:
        """命令生效后，把意图记到**这条命令真正涉及**的单位的进度上。

        不能记到本次调用的全部单位：一条命令只针对一个对象时，记错会把别的单位
        的目标格覆盖掉。
        """
        covered = set(intent.units)
        affected = [unit for unit in squad.units if unit.agent_id in covered]
        if intent.kind == "move_to":
            for unit in affected:
                unit.goal = tuple(intent.cell)
                unit.mode = UnitMode.MOVING
                # 重新下令即重新计时，免得下拍立刻又被判为卡住
                unit.last_change_frame = state.frame
        elif intent.kind == "attack":
            for unit in affected:
                unit.mode = UnitMode.ENGAGING
                unit.target = intent.target
                unit.goal = None
        else:
            # 停止、生产、放置、变卖、部署：命令生效即算到位
            for unit in affected:
                unit.mode = UnitMode.ARRIVED
                unit.goal = None

    @staticmethod
    def _needs_orders(unit) -> bool:
        """这个单位现在要不要下令。"""
        if unit.mode == UnitMode.STUCK:
            return True
        return unit.mode == UnitMode.MOVING and unit.goal is None

    def _fail_squad(self, squad, observation, outcomes, reason) -> None:
        """整队失败。"""
        for unit in squad.units:
            if unit.mode not in DONE_MODES:
                unit.mode = UnitMode.FAILED
        self._record(observation.frame, "squad_failed", squad.intent,
                     {"tactic": squad.intent.tactic, "reason": reason})
        # 结算交给紧随其后的 _settle：一处收尾，免得同一条编队被记两次
        squad.intent.state = IntentState.FAILED

    def _record(self, frame, event, intent, detail) -> None:
        """写决策日志。"""
        if self.log is None:
            return
        self.log.record(frame, event, intent=intent, detail=detail)


def _within(cell, goal, radius) -> bool:
    """两格的切比雪夫距离是否在宽容范围内。"""
    return abs(cell[0] - goal[0]) <= radius and abs(cell[1] - goal[1]) <= radius
