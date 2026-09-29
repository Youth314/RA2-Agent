"""自动触发的测试。

机制的核心是：技法按名片里的触发声明自己跑，产出**脉冲**（跑一次、下发一次、
不建编队），且**与模型调用共用同一道门槛**——触发层不是后门。
"""
import unittest

from ra2agent.autopilot import Autopilot, kind_of
from ra2agent.errors import CommandFailed, TacticError
from ra2agent.events import Event, EventKind, Subject
from ra2agent.intents import Deploy
from ra2agent.observation import Observation
from ra2agent.state import GameState
from ra2agent.tactics import (Level, Param, Tactic, TacticInfo, TacticPolicy,
                              TacticRegistry, Trigger)
from tests.fixtures import PLAYER_HOUSE, build_game_state, build_house


class FakeSubject:
    """脉冲用的 subject：把若干 agent id 当成一队。"""

    def __init__(self, agents=(1, 2)):
        self._agents = tuple(agents)

    def agents(self):
        return self._agents

    def object_of(self, agent_id):
        return None

    def agent_id(self, pointer):
        return None

    def cell_of(self, agent_id):
        return None


class FakeExecutor:
    """记账用的假执行器；可指定某条意图抛错。"""

    def __init__(self, fail_on=None):
        self.executed = []
        self.fail_on = fail_on or ()

    def execute(self, intent, state):
        self.executed.append(intent)
        if intent.kind in self.fail_on:
            raise CommandFailed(f"{intent.kind} 失败")
        return type("Outcome", (), {"state": object(), "frames_waited": 4})()


def observation(frame=100):
    state = GameState.parse(build_game_state(
        houses=[build_house(PLAYER_HOUSE, current_player=True)], frame=frame))
    return Observation(frame=state.frame, house=state.player_house(), state=state)


def event(kind, frame=100):
    return Event(kind=kind, frame=frame, subject=Subject("house", 0, "me"))


def tactic(name, run, trigger=None, **kwargs):
    return Tactic(TacticInfo(name=name, summary=f"{name} 的说明",
                             trigger=trigger or Trigger.every(30), **kwargs), run)


class AutopilotCase(unittest.TestCase):
    def build(self, tactics, executor=None):
        self.registry = TacticRegistry().load(tactics)
        self.executor = executor or FakeExecutor()
        self.autopilot = Autopilot(self.registry, self.executor)
        return self.autopilot

    def subject(self):
        return FakeSubject()


class TestTriggerEvaluation(AutopilotCase):
    def test_first_tick_fires_an_interval_trigger(self):
        # 「开局立刻」要的正是这个：第一次有机会就跑
        self.build([tactic("a", lambda ctx: ())])
        self.assertEqual([t.info.name for t in self.autopilot.due(observation(), ())], ["a"])

    def test_interval_is_respected_before_the_next_run(self):
        self.build([tactic("a", lambda ctx: (), Trigger.every(30))])
        self.autopilot.run(observation(frame=100), (), self.subject())
        self.assertEqual(self.autopilot.due(observation(frame=110), ()), ())
        self.assertEqual([t.info.name for t in
                          self.autopilot.due(observation(frame=130), ())], ["a"])

    def test_event_trigger_fires_only_on_that_event(self):
        self.build([tactic("a", lambda ctx: (), Trigger.on(EventKind.LOW_POWER))])
        self.assertEqual(self.autopilot.due(observation(), ()), ())
        self.assertEqual(len(self.autopilot.due(
            observation(), (event(EventKind.LOW_POWER),))), 1)

    def test_other_events_do_not_fire_it(self):
        self.build([tactic("a", lambda ctx: (), Trigger.on(EventKind.LOW_POWER))])
        self.assertEqual(self.autopilot.due(
            observation(), (event(EventKind.INSUFFICIENT_FUNDS),)), ())

    def test_plain_tactics_are_never_automatic(self):
        self.build([tactic("a", lambda ctx: (), Trigger())])
        self.assertEqual(self.registry.automatic(), ())
        self.assertEqual(self.autopilot.due(observation(), ()), ())

    def test_event_kind_strings_are_accepted(self):
        self.build([tactic("a", lambda ctx: (), Trigger.on("low_power"))])
        self.assertEqual(len(self.autopilot.due(
            observation(), (event(EventKind.LOW_POWER),))), 1)

    def test_kind_of_handles_plain_strings(self):
        self.assertEqual(kind_of(event(EventKind.LOW_POWER)), "low_power")
        self.assertEqual(kind_of("low_power"), "low_power")

    def test_both_declarations_fire_on_either(self):
        trigger = Trigger.automatic(EventKind.LOW_POWER, every_frames=30)
        self.build([tactic("a", lambda ctx: (), trigger)])
        self.assertEqual(len(self.autopilot.due(observation(), ())), 1, "定时先到")
        self.autopilot.run(observation(frame=100), (), self.subject())
        self.assertEqual(len(self.autopilot.due(
            observation(frame=101), (event(EventKind.LOW_POWER),))), 1, "事件也到")


class TestPulse(AutopilotCase):
    def test_intents_are_dispatched_once(self):
        self.build([tactic("a", lambda ctx: (ctx.intent(Deploy, units=(1,)),))])
        records = self.autopilot.run(observation(), (), self.subject())
        self.assertEqual(len(self.executor.executed), 1)
        self.assertEqual(records[0]["intents"], 1)
        self.assertEqual(records[0]["outcomes"][0]["state"], "已生效")

    def test_a_tactic_may_decide_to_do_nothing(self):
        # 技法自己判断此刻无事可做——常见且正常，故标 idle 而不报给模型
        self.build([tactic("a", lambda ctx: ())])
        records = self.autopilot.run(observation(), (), self.subject())
        self.assertTrue(records[0]["idle"])
        self.assertEqual(self.executor.executed, [])

    def test_dispatch_failure_is_recorded_not_raised(self):
        self.build([tactic("a", lambda ctx: (ctx.intent(Deploy, units=(1,)),))],
                   FakeExecutor(fail_on=("deploy",)))
        records = self.autopilot.run(observation(), (), self.subject())
        self.assertIn("error", records[0]["outcomes"][0])

    def test_one_failure_does_not_stop_the_rest(self):
        self.build([tactic("a", lambda ctx: (ctx.intent(Deploy, units=(1,)),
                                             ctx.intent(Deploy, units=(2,)),))],
                   FakeExecutor(fail_on=("deploy",)))
        records = self.autopilot.run(observation(), (), self.subject())
        self.assertEqual(len(records[0]["outcomes"]), 2, "两条都试过了")

    def test_records_are_bounded(self):
        self.build([tactic("a", lambda ctx: ())])
        self.autopilot.max_records = 3
        for frame in range(100, 220, 30):
            self.autopilot.run(observation(frame), (), self.subject())
        self.assertLessEqual(len(self.autopilot.records), 3)


class TestAdmissionIsShared(AutopilotCase):
    """触发层不是后门：等级门槛与停用名单一样管用。"""

    def test_disabled_tactic_is_not_run(self):
        policy = TacticPolicy(disabled=frozenset({"a"}))
        self.registry = TacticRegistry(policy=policy).load([tactic("a", lambda ctx: ())])
        self.executor = FakeExecutor()
        self.autopilot = Autopilot(self.registry, self.executor)
        records = self.autopilot.run(observation(), (), self.subject())
        self.assertEqual(self.executor.executed, [])
        self.assertIn("停用", records[0]["skipped"])

    def test_level_ceiling_applies(self):
        from ra2agent.intents import Layer
        # NORMAL 的技法在 CHEAT 门槛下也允许，故把门槛压到最低的那一档来验拦截
        policy = TacticPolicy(max_level={Layer.L1_TACTIC: Level.NORMAL})
        self.registry = TacticRegistry(policy=policy).load(
            [tactic("a", lambda ctx: (), level=Level.EXPLOIT)])
        self.executor = FakeExecutor()
        self.autopilot = Autopilot(self.registry, self.executor)
        records = self.autopilot.run(observation(), (), self.subject())
        self.assertEqual(self.executor.executed, [])
        self.assertIn("门槛", records[0]["skipped"])

    def test_missing_condition_skips_it(self):
        # has_units 靠 subject；给个空 subject 就不该跑
        self.build([tactic("a", lambda ctx: (ctx.intent(Deploy, units=(1,)),),
                           requires=("has_units",))])
        records = self.autopilot.run(observation(), (), FakeSubject(agents=()))
        self.assertEqual(self.executor.executed, [])
        self.assertIn("用不上", records[0]["skipped"])


class TestTriggerValidation(unittest.TestCase):
    def test_negative_interval_is_rejected(self):
        with self.assertRaises(TacticError):
            TacticRegistry().load([tactic("a", lambda ctx: (), Trigger.every(-1))])

    def test_never_runnable_is_rejected(self):
        with self.assertRaises(TacticError):
            TacticRegistry().load([tactic("a", lambda ctx: (), Trigger(on_call=False))])

    def test_required_params_are_rejected_for_automatic_tactics(self):
        # 自动触发时模型不在场，没人填必填参数
        with self.assertRaises(TacticError):
            TacticRegistry().load([tactic("a", lambda ctx: (), Trigger.every(30),
                                          params=(Param("cell"),))])

    def test_defaulted_params_are_fine(self):
        TacticRegistry().load([tactic("a", lambda ctx: (), Trigger.every(30),
                                      params=(Param("radius", 3),))])


if __name__ == "__main__":
    unittest.main()
