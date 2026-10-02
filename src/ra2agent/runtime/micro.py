"""L1 运行时：按 tick 跑技法，把意图交给基础设施，并跟踪进度。

技法只回答「这一步该下什么命令」；其余全在这里：谁需要下令、命令是否生效、卡住
怎么办、任务何时算完成或失败。

按 tick 而不是逐帧跑：单帧观测 11.9 KB，逐帧轮询不值，且寻路与自动开火由引擎
负责。默认每 22 帧（约 0.5 秒）一拍。
"""
import time
from dataclasses import dataclass, replace
from enum import StrEnum

from ..constants import WAIT_GRACE_FRAMES
from ..errors import (CommandFailed, GameNotResponding, InvalidCommand, Timeout,
                     TacticDenied, TacticError)
from .executor import Executor
from .intents import (IntentState, Stance, TacticCall, check_command_scope,
                      command_actors, split_wakes)
from ..engine.observation import Observation
from ..tactics import Mode, TacticRegistry
from ..engine.validate import Validator
from ..wake import WakeBridge

#: 每 tick 之间的默认帧数。44 fps 下约 0.5 秒。
DEFAULT_TICK_FRAMES = 22
#: 到位宽容（格）。引擎在目标格被占时会停在邻格。
DEFAULT_ARRIVE_RADIUS = 1
#: 位置多少帧不动就算卡住。
DEFAULT_STUCK_FRAMES = 90
#: 一条命令最多重试几次。
DEFAULT_MAX_RETRIES = 3
#: 同类运行时告警最短间隔（帧）。每拍都发同一条只会把 `status` 撑爆
#: （实测单次堆过 20 条「等待」）。
NOTICE_EVERY_FRAMES = 600


class UnitMode(StrEnum):
    """一个单位在任务中的状态。"""

    MOVING = "moving"        # 已下令，尚未到位
    ENGAGING = "engaging"    # 正在接战
    ARRIVED = "arrived"      # 已到位
    STUCK = "stuck"          # 位置长时间不动，等换路点
    LOST = "lost"            # 对象从观测里消失
    FAILED = "failed"        # 命令反复失败
    UNVERIFIED = "unverified"  # 已提交，结果未知；禁止自动重发


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
    completion_basis: str | None = None


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
        #: 从哪一帧起连续等同一个理由；理由一变就重新计时。
        self.wait_since: int | None = None
        self.wait_key: str = ""
        #: 这条任务**第一次**开始等待的帧。与 `wait_since` 的区别是它不被理由变化
        #: 重置：理由在两种之间来回摆时（条件时有时无），按理由计时会永远到不了上限
        #: ——实测一条 `place_ready_building` 因此挂了 4700 多帧，占着建造厂不放，
        #: 后续所有建造都被拒「这个厂正忙」。
        self.wait_started: int | None = None
        #: 每类告警上次发出的帧，用于限频（见 `_notify_once`）。
        self.notice_frames: dict = {}
        self.pending: list = []
        self.receipts: list = []

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
                 max_retries=DEFAULT_MAX_RETRIES, sleep=time.sleep, wake=None):
        self.observer = observer
        self.registry = registry or TacticRegistry(log=log).load_builtin()
        self.log = log
        self.tick_frames = tick_frames
        self.arrive_radius = arrive_radius
        self.stuck_frames = stuck_frames
        self.max_retries = max_retries
        self._sleep = sleep
        #: 唤醒桥。**一个会话一份**，自动层与模型调用的路径共用同一份额度。
        self.wake = wake if wake is not None else WakeBridge(log=log)
        self._squads: list = []
        #: 已结算的任务，供指挥层读取
        self.completed: list = []
        #: 值得一提的运行时事件（失焦暂停、条件变化导致空转），供指挥层上报
        self.notices: list = []
        self.last_tick_frame: int | None = None
        #: 每拍开头的钩子，自动触发挂在这。指挥层建好后设上。
        self.on_tick = None
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
        busy = {u.agent_id for squad in self._squads for u in squad.units}
        overlap = busy.intersection(call.scope.objects)
        if overlap:
            raise TacticError(f"对象已被其他任务占用：{sorted(overlap)}")
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
        """走一拍：更新进度、按需调用技法、下发意图。返回本拍的执行结果。

        直接调用不会检查帧是否推进；循环驱动的 `run()` 会，故游戏暂停时不下令。
        暂停时下的令会留在队列里，等恢复后才执行，那时已脱离本次意图的语境。
        """
        observation = observation if observation is not None else self.observer.poll()
        # 自动触发排在编队循环之前，这样本拍发起的任务同拍就能下令
        if self.on_tick is not None:
            self.on_tick(observation)
        outcomes = []
        for squad in list(self._squads):
            self._update(squad, observation)
            if self._settle(squad, observation, outcomes):
                continue
            self._order(squad, observation, outcomes)
            # 同步执行可能等待了多帧；结算不能早于最新回执。
            if outcomes and outcomes[-1].state.frame > observation.frame:
                latest = outcomes[-1].state
                observe = getattr(self.observer, "observe", None)
                current = observe() if observe is not None else None
                observation = (current if current is not None and current.frame >= latest.frame
                               else replace(observation, frame=latest.frame, state=latest))
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

    def progress(self) -> tuple:
        """在管任务的进度摘要，供指挥层读给模型。"""
        out = []
        for squad in self._squads:
            counts: dict = {}
            for unit in squad.units:
                counts[str(unit.mode)] = counts.get(str(unit.mode), 0) + 1
            out.append({
                "intent_id": squad.intent.id,
                "tactic": squad.intent.tactic,
                "units": [unit.agent_id for unit in squad.units],
                "created_frame": squad.intent.created_frame,
                "modes": counts,
                "receipts": list(squad.receipts),
                "unverified": len(squad.pending),
            })
        return tuple(out)

    def cancel(self, intent_id) -> bool:
        """撤销一条在管任务，交还它占用的单位。已结束或不存在时返回假。"""
        for squad in list(self._squads):
            if squad.intent.id != intent_id:
                continue
            squad.intent.state = IntentState.SUPERSEDED
            # 不动单位的状态：任务撤了不等于到位，结算里就不该记到位
            self._finish(squad, squad._observation, [], IntentState.SUPERSEDED)
            return True
        return False

    def cards(self, observation, squad=None):
        """此刻该给模型看的卡片。"""
        return self.registry.cards(Mode.MATCH, observation, squad)

    # ------------------------------------------------------------ 进度
    def _update(self, squad, observation) -> None:
        """按最新观测推进每个单位的状态。"""
        state = observation.state
        for pending in list(squad.pending):
            plan = pending.get("plan")
            if plan is not None and plan.verify(state):
                self._advance(squad, pending["intent"], state)
                squad.pending.remove(pending)
                squad.receipts.append({"intent_id": pending["intent"].id,
                                       "receipt": "observed_match",
                                       "evidence": "late_match", "frame": state.frame})
        enemies = {self.observer.identity.agent_id(obj.pointer)
                   for obj in observation.visible_enemies}
        for unit in squad.units:
            if unit.mode in DONE_MODES:
                continue
            pointer = self.observer.identity.pointer_of(unit.agent_id)
            if pointer is None:
                unit.mode = UnitMode.LOST
                continue
            unit.pointer = pointer
            found = state.object(unit.pointer)
            if found is None:
                unit.mode = UnitMode.LOST
                continue
            if unit.mode == UnitMode.UNVERIFIED:
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
                    unit.completion_basis = "goal_satisfied"
                elif observation.frame - unit.last_change_frame >= self.stuck_frames:
                    # 卡住就换路点：计数加一，下拍按 attempt 换一个落点
                    unit.retries += 1
                    unit.mode = (UnitMode.FAILED if unit.retries > self.max_retries
                                 else UnitMode.STUCK)

    def _settle(self, squad, observation, outcomes) -> bool:
        """任务结束就结算并移出，返回是否已结束。"""
        if squad.intent.is_expired(observation.frame):
            squad.intent.state = IntentState.EXPIRED
            self._finish(squad, observation, outcomes, IntentState.EXPIRED,
                         reason="超过有效期")
            return True
        if any(unit.mode not in DONE_MODES for unit in squad.units):
            return False
        arrived = sum(1 for unit in squad.units if unit.mode == UnitMode.ARRIVED)
        state = (IntentState.SATISFIED if arrived == len(squad.units)
                 else IntentState.FAILED)
        squad.intent.state = state
        self._finish(squad, observation, outcomes, state,
                     reason=getattr(squad.intent, "fail_reason", ""))
        return True

    def _finish(self, squad, observation, outcomes, state, reason="") -> None:
        """收尾：记结算、移出编队。

        `reason` 是失败原因的人话。不给的话「失败 2 个」对模型没有信息量——它只能
        猜是钱不够、落点被占，还是对象没了。原因同时进决策日志与 `status`。
        """
        record = {
            "intent_id": squad.intent.id,
            "tactic": squad.intent.tactic,
            "state": str(state),
            "frame": (observation.frame if observation is not None
                      else squad.intent.created_frame),
            "arrived": [u.agent_id for u in squad.units if u.mode == UnitMode.ARRIVED],
            "lost": [u.agent_id for u in squad.units if u.mode == UnitMode.LOST],
            "failed": [u.agent_id for u in squad.units if u.mode == UnitMode.FAILED],
            "reason": reason,
            "receipts": list(squad.receipts),
            "unverified": len(squad.pending),
            "completion_basis": {u.agent_id: u.completion_basis for u in squad.units
                                 if u.completion_basis is not None},
        }
        self.completed.append(record)
        self._squads.remove(squad)
        self._record(record["frame"], "squad_settled", squad.intent, record)

    # ------------------------------------------------------------ 下令
    def _order(self, squad, observation, outcomes) -> None:
        """对需要下令的单位跑一次技法。"""
        if squad.pending:
            return
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
            # 条件不满足：等局面变化，但**有上限**（见 `_wait`）
            self._wait(squad, observation, outcomes, str(error))
            return
        except TacticError as error:
            self._fail_squad(squad, observation, outcomes, str(error))
            return
        # `Wake` 不落到引擎——它往上走，交给唤醒桥
        engine, wakes = split_wakes(intents)
        if not engine:
            # 条件过了却一条意图都没有：要么这条技法本就「无事可做」（展开基地车
            # 打非基地车），要么它在等下一拍（区域防守等目标、建筑还在造时还不够
            # 放下）。前者当场收工；后者也算「等局面变化」，**同样有上限**——
            # 否则一条等楼完工的任务会在楼烂尾时永久占着单位。
            if self.registry.get(squad.intent.tactic).info.idle_ends_task:
                self._idle_squad(squad, observation, outcomes)
            else:
                self._wait(squad, observation, outcomes,
                           "技法此刻没有可执行的（条件成立但无事可做）")
            return
        squad.wait_since = None            # 又动起来了，等待计时归零
        squad.wait_key = ""
        squad.wait_started = None
        for intent in wakes:
            self._request_wake(intent, observation, squad.intent.tactic)
        for intent in engine:
            self._dispatch(squad, active, intent, observation, outcomes)
            if squad.pending or squad.intent.is_terminal():
                break

    def _wait(self, squad, observation, outcomes, reason) -> None:
        """条件没满足时的一次等待：记日志、限频告警、等太久就收工。

        旧写法只记不结：一条「等建筑完工」的任务能永久占着单位（实测 `deploy_mcv`
        挂过两千多帧），而每拍都发同一条告警——单次 `status` 堆过 20 条。等的前提
        变了就重新计时，故正常等待（造楼那几百帧）不会被误收。
        """
        frame = observation.frame
        if squad.wait_since is None or squad.wait_key != reason:
            squad.wait_since = frame
            squad.wait_key = reason
        if squad.wait_started is None:
            squad.wait_started = frame
        self._record(frame, "squad_waiting", squad.intent,
                     {"tactic": squad.intent.tactic, "reason": reason})
        self._notify_once(squad, "waiting", frame, squad.intent.tactic, reason)
        grace = self.registry.get(squad.intent.tactic).info.wait_grace_frames
        # 按**首次等待**算，不按当前这段理由：理由摆动不该无限续命
        waited = frame - squad.wait_started
        if grace is not None and waited >= grace:
            self._fail_squad(squad, observation, outcomes,
                             f"等了 {waited} 帧局面没变：{reason}")

    def _idle_squad(self, squad, observation, outcomes) -> None:
        """技法明说此刻无事可做：当场收工，把单位交还。

        **不算失败**：单位没出错，只是这条技法对它们没有可做的事（例如对一台已经
        展开的建造厂再喊 `deploy_mcv`）。单位状态不动，故结算里也不会记到位。
        """
        squad.intent.state = IntentState.IDLE
        self._finish(squad, observation, outcomes, IntentState.IDLE,
                     reason="此刻无事可做，已交还单位")

    def _request_wake(self, intent, observation, tactic) -> None:
        """把一条 `Wake` 意图投给桥。投递失败不改任务状态——它是旁路，不是命令。"""
        record = self.wake.request(intent.text, observation.frame, tactic=tactic)
        self._record(observation.frame, "wake_requested", intent, record)

    def _dispatch(self, squad, active, intent, observation, outcomes) -> None:
        """下发一条意图，并按结果更新进度。"""
        affected_ids = set(command_actors(intent) or intent.scope.objects)
        affected = [unit for unit in active if unit.agent_id in affected_ids]
        try:
            if intent.parent is None:
                intent.parent = squad.intent.id
            check_command_scope(intent, [u.agent_id for u in active],
                                state=observation.state,
                                identity=self.observer.identity)
            outcome = self.executor.execute(intent, observation.state)
        except (GameNotResponding, Timeout) as error:
            # 等待超时或失焦均不能证明命令没执行，保留请求等待后续观测。
            squad.pending.append({"intent": intent,
                                  "plan": getattr(error, "plan", None)})
            for unit in affected or active:
                unit.mode = UnitMode.UNVERIFIED
            self._record(observation.frame, "command_unverified", squad.intent,
                         {"intent": intent.kind, "reason": str(error)})
            self._notify_once(squad, "unverified", observation.frame,
                              squad.intent.tactic, str(error))
            return
        except CommandFailed as error:
            if error.reason in ("object_missing", "illegal_mission"):
                for unit in affected:
                    unit.mode = UnitMode.FAILED
            else:
                self._fail_squad(squad, observation, outcomes, str(error))
            return
        except InvalidCommand as error:
            self._fail_squad(squad, observation, outcomes, str(error))
            return
        outcomes.append(outcome)
        squad.receipts.append({"intent_id": intent.id,
                               "receipt": outcome.receipt,
                               "evidence": outcome.evidence,
                               "frame": outcome.state.frame})
        self._advance(squad, intent, outcome.state)

    def _advance(self, squad, intent, state) -> None:
        """操作判据成立后，把意图记到**这条命令真正涉及**的单位的进度上。

        不能记到本次调用的全部单位：一条命令只针对一个对象时，记错会把别的单位
        的目标格覆盖掉。

        `Produce` / `Place` / `Sell` 不针对对象，**没有 `units` 字段**：它们的归属
        在信封的 `scope` 里。不退回 `scope` 的话，这三种意图一执行成功就抛
        `AttributeError`，整拍崩掉——而「命令生效即算到位」本来也正是要把这次点名
        的单位交还出去。
        """
        units = getattr(intent, "units", None)
        covered = set(intent.scope.objects if units is None else units)
        affected = [unit for unit in squad.units if unit.agent_id in covered]
        if intent.kind == "move_to" and intent.stance != Stance.HOLD:
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
            # 一次操作按观测结算；Guard 的输入确认不表示抵达或持续保护。
            for unit in affected:
                unit.mode = UnitMode.ARRIVED
                unit.goal = None
                unit.completion_basis = "operation_observed"

    @staticmethod
    def _needs_orders(unit) -> bool:
        """这个单位现在要不要下令。"""
        if unit.mode == UnitMode.STUCK:
            return True
        return unit.mode == UnitMode.MOVING and unit.goal is None

    def _fail_squad(self, squad, observation, outcomes, reason) -> None:
        """整队失败。

        `reason` 记在意图上，等紧随其后的 `_settle` 收尾时带进 `completed`——
        否则模型只看到「失败 N 个」，永远不知道是钱不够还是落点被占。
        """
        for unit in squad.units:
            if unit.mode not in DONE_MODES:
                unit.mode = UnitMode.FAILED
        squad.intent.fail_reason = reason
        self._record(observation.frame, "squad_failed", squad.intent,
                     {"tactic": squad.intent.tactic, "reason": reason})
        # 结算交给紧随其后的 _settle：一处收尾，免得同一条编队被记两次
        squad.intent.state = IntentState.FAILED

    def _notify(self, kind, frame, tactic, detail) -> None:
        """记一条运行时告警，等着指挥层报给模型。"""
        self.notices.append({"kind": kind, "frame": frame, "tactic": tactic,
                             "detail": detail})

    def _notify_once(self, squad, kind, frame, tactic, detail, *,
                     every=NOTICE_EVERY_FRAMES) -> None:
        """同一类告警按帧限频：局面没变就别每拍说一遍。

        理由变了立刻放行（那是新信息）；否则最快 `every` 帧一条。告警是给模型看的
        信号，不是日志——重复的告警只会把真有事的那几条淹掉。
        """
        key = f"{kind}:{detail}"
        last = squad.notice_frames.get(kind)
        if last is not None and key == squad.notice_frames.get(f"{kind}:key"):
            if frame - last < every:
                return
        squad.notice_frames[kind] = frame
        squad.notice_frames[f"{kind}:key"] = key
        self._notify(kind, frame, tactic, detail)

    def _record(self, frame, event, intent, detail) -> None:
        """写决策日志。"""
        if self.log is None:
            return
        self.log.record(frame, event, intent=intent, detail=detail)


def _within(cell, goal, radius) -> bool:
    """两格的切比雪夫距离是否在宽容范围内。"""
    return abs(cell[0] - goal[0]) <= radius and abs(cell[1] - goal[1]) <= radius
