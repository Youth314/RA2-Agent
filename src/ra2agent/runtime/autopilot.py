"""自动触发：技法按自己在名片里声明的触发条件跑起来。

产出的是**脉冲**——跑一次、下发一次、不建编队。三处理由见 `Trigger` 的文档：
房子级动作不需要单位，绑一队单位会让 `Produce` 每拍重发，而脉冲也不会长期占着
单位的租约。

**与模型调用共用同一道门槛**：`TacticRegistry.run` 里的策略闸与适用条件闸一项不少。
触发层不是后门——等级门槛、停用名单、适用条件，自动触发一样要过。
"""
from ..errors import GameNotResponding, InvalidCommand, Ra2Error, Timeout
from .intents import check_command_scope, command_actors, split_wakes
from ..wake import WakeBridge

#: 保留多少条自动执行记录给 `status` 查。
DEFAULT_MAX_RECORDS = 64


def kind_of(event) -> str:
    """事件类型名。`EventKind` 是 `str` 枚举，但字符串也认。"""
    kind = getattr(event, "kind", event)
    return str(getattr(kind, "value", kind))


class Autopilot:
    """按触发声明跑技法。由技法层每拍驱动一次。"""

    def __init__(self, registry, executor, log=None, wake=None,
                 max_records=DEFAULT_MAX_RECORDS, available=None):
        self.registry = registry
        self.executor = executor
        self.log = log
        self.wake = wake if wake is not None else WakeBridge(log=log)
        self.max_records = max_records
        #: 技法名 → 上次跑的帧。`every` 靠它计时。
        self._last_run: dict = {}
        #: 自动脉冲共用的记事本。脉冲每拍新建上下文，故**跨帧记忆只能放这里**：
        #: `economy.auto_harvest` 用它记住「刚把哪台矿车派去了哪片矿」，免得每拍重发
        #: 同一条移动令把它钉在原地。
        self.memo: dict = {}
        self.records: list = []
        self.available = available
        self.pending: dict = {}

    # ------------------------------------------------------------ 判断
    def due(self, observation, events) -> tuple:
        """这一拍该跑哪些技法。只读，不改状态。"""
        kinds = {kind_of(event) for event in events}
        out = []
        for tactic in self.registry.automatic():
            if self.triggers(tactic.info.trigger, tactic.info.name, observation, kinds):
                out.append(tactic)
        return tuple(out)

    def triggers(self, trigger, name, observation, kinds) -> bool:
        """这条触发声明此刻命中没有。"""
        # 两侧都过 `kind_of`：`str(EventKind.LOW_POWER)` 给的是 'EventKind.LOW_POWER'，
        # 而不是它假装的那个字符串值
        if trigger.events and kinds & {kind_of(kind) for kind in trigger.events}:
            return True
        if trigger.every_frames:
            # 没跑过的先跑一次——「开局立刻」要的正是这个
            last = self._last_run.get(name)
            return last is None or observation.frame - last >= trigger.every_frames
        return False

    # ------------------------------------------------------------ 执行
    def run(self, observation, events, subject) -> tuple:
        """跑这一拍该跑的技法，下发它们产出的意图。返回本拍记录。"""
        self.wake.update(observation, getattr(subject, "identity", None))
        records = []
        for tactic in self.due(observation, events):
            self._last_run[tactic.info.name] = observation.frame
            records.append(self._pulse(tactic, observation, subject, events))
        if records:
            self.records.extend(records)
            del self.records[:-self.max_records]
        return tuple(records)

    def _pulse(self, tactic, observation, subject, events=()):
        """跑一条技法并把它的意图各下发一次。"""
        name = tactic.info.name
        record = {"tactic": name, "frame": observation.frame, "kind": "pulse"}
        pending = self.pending.get(name)
        if pending is not None:
            _, plan = pending
            if plan is not None and plan.verify(observation.state):
                del self.pending[name]
                record["receipt"] = "observed_match"
                record["evidence"] = "late_match"
            record["skipped"] = ("未知结果已观测匹配，本拍不再提交" if name not in self.pending
                                 else "先前命令结果未知，等待观测，不自动重发")
            self._log(observation, "auto_unverified", record)
            return record
        # 门槛由 registry.run 强制执行；先问一次只为把「为什么没跑」记清楚。
        # 脉冲没有调用方给参数，故条件按补好的默认值判——自动触发的技法不许有必填参数
        reason = self.registry.admit(
            name, observation, subject,
            self.registry.check_params(name, {}))
        if reason:
            record["skipped"] = reason
            self._log(observation, "auto_skipped", record)
            return record
        try:
            intents = self.registry.run(name, observation=observation,
                                        subject=subject, frame=observation.frame,
                                        memo=self.memo, events=events)
        except Ra2Error as error:
            record["error"] = str(error)
            self._log(observation, "auto_failed", record)
            return record
        record["intents"] = len(intents)
        if not intents:
            # 技法自己判断此刻无事可做——常见且正常，不必报给模型
            record["idle"] = True
            return record
        # `Wake` 不落到引擎——它往上走，交给唤醒桥
        engine, wakes = split_wakes(intents)
        if engine:
            record["outcomes"] = self._dispatch(engine, observation, record, subject)
        if wakes:
            record["wakes"] = list(self.wake.request_many(
                ((intent.text, intent.placement_building) for intent in wakes),
                observation.frame, tactic=name))
        self._log(observation, "auto_ran", record)
        return record

    def _dispatch(self, intents, observation, record, subject) -> list:
        """逐条下发。单条失败不影响其余。"""
        outcomes = []
        for intent in intents:
            entry = {"intent": intent.kind}
            try:
                allowed = set(subject.agents())
                check_command_scope(intent, allowed, state=observation.state,
                                    identity=getattr(subject, "identity", None))
                if self.available is not None:
                    available = set(self.available())
                    if not set(command_actors(intent) + intent.scope.objects) <= available:
                        raise InvalidCommand("自动触发操作对象已被在管任务占用")
                outcome = self.executor.execute(intent, observation.state)
            except (GameNotResponding, Timeout) as error:
                # 失焦不是命令失败：整拍挂起，别把剩下的也发了
                record["paused"] = str(error)
                self.pending[record["tactic"]] = (intent, getattr(error, "plan", None))
                entry["state"] = "结果未知"
                entry["error"] = str(error)
                outcomes.append(entry)
                break
            except Ra2Error as error:
                entry["error"] = str(error)
                outcomes.append(entry)
                continue
            # `outcome.state` 是判据成立时的那一帧局面，不是意图状态，别拿来渲染
            entry["state"] = "观测匹配"
            entry["receipt"] = getattr(outcome, "receipt", "observed_match")
            entry["evidence"] = getattr(outcome, "evidence", "unknown")
            entry["waited"] = outcome.frames_waited
            outcomes.append(entry)
        return outcomes

    def _log(self, observation, event, record) -> None:
        """写进决策日志。`issuer` 标成自动层，复盘时分得清是谁干的。"""
        if self.log is None:
            return
        self.log.record(observation.frame, event,
                        detail={"issuer": f"trigger:{record.get('kind', 'pulse')}",
                                **record})
