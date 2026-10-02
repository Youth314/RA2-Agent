"""S4 技法迁移：真实受理/执行路径与自动脉冲；离线测试不证明游戏效果。"""
from dataclasses import replace
import unittest

from ra2agent.command import CallRequest, Commander, UnitPool
from ra2agent.constants import AbstractType, Mission
from ra2agent.engine.observation import Observer
from ra2agent.engine.validate import Validator
from ra2agent.errors import TacticDenied
from ra2agent.runtime.autopilot import Autopilot
from ra2agent.runtime.executor import Executor
from ra2agent.runtime.micro import MicroLayer
from ra2agent.tactics import TacticRegistry
from tests.test_autopilot import FakeExecutor, TimeoutExecutor
from tests.test_executor import TANK
from tests.test_field_tactics import (MINER_TYPE, make_catalogue, make_map,
                                     make_types)
from tests.test_guard_interface import GuardClient, NATIVE_ID, event, state


def miner_state(frame=100, *, mission=Mission.STOP, version=1, native_id=NATIVE_ID,
                events=()):
    return state(frame, events, version, mission=mission,
                 type_pointer=MINER_TYPE, native_id=native_id)


class GuardTacticCase(unittest.TestCase):
    def build(self, initial=None, after=None, *, names=("native_guard",)):
        initial = initial if initial is not None else state()
        after = after if after is not None else state(101, [event(cell=(1, 1))])
        self.client = GuardClient([initial, after])
        self.observer = Observer(self.client, map_data=make_map(), types=make_types(),
                                 catalogue=make_catalogue())
        self.obs = self.observer.poll()
        self.agent = self.observer.identity.agent_id(TANK)
        builtin = TacticRegistry().load_builtin()
        self.registry = TacticRegistry().load(builtin.get(name) for name in names)
        self.executor = Executor(self.client, self.observer.identity,
                                 validator=Validator(self.observer.map_data),
                                 read_state=lambda: self.observer.poll().state,
                                 sleep=lambda _: self.client.advance())
        self.layer = MicroLayer(self.observer, self.registry, self.executor)
        self.commander = Commander(self.layer, self.observer)

    def pool(self, obs=None, excluded=()):
        return UnitPool(obs or self.obs, self.observer.identity, excluded=excluded)

    def call(self, name="native_guard", params=None, units=None, observation=None):
        return self.commander.call([CallRequest(
            tactic=name, units=(self.agent,) if units is None else units,
            params=params or {})], observation or self.obs)[0]


class TestNativeGuard(GuardTacticCase):
    def test_current_pool_and_squad_paths_confirm_only_input(self):
        self.build()
        intents = self.registry.run("native_guard", observation=self.obs,
                                    subject=self.pool(), frame=self.obs.frame)
        self.assertEqual([i.kind for i in intents], ["guard_current"])
        accepted = self.call()
        self.assertTrue(accepted.accepted, accepted.error)
        outcomes = self.layer.tick(self.obs)
        self.assertEqual(outcomes[0].evidence, "native_input_observed")
        completed = self.layer.completed[-1]
        self.assertEqual(completed["completion_basis"], {self.agent: "operation_observed"})
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(len(self.client.sent), 1)
        self.layer.tick(self.observer.observe())
        self.assertEqual(len(self.client.sent), 1, "已释放任务不重复原生输入")
        self.assertFalse(self.layer.cancel(accepted.intent_id))
        self.assertEqual(len(self.client.sent), 1, "结算后 cancel 不发 Stop")

    def test_position_does_not_wait_for_arrival(self):
        self.build(after=state(101, [event(cell=(2, 2))]))
        accepted = self.call(params={"cell": [2, 2]})
        self.assertTrue(accepted.accepted, accepted.error)
        outcomes = self.layer.tick(self.obs)
        self.assertEqual(outcomes[0].kind, "guard_position")
        self.assertEqual(self.observer.last_state.object(TANK).coordinates.cell, (1, 1))
        self.assertEqual(self.layer.squads(), ())

    def test_unknown_native_input_keeps_lease_and_late_match_does_not_resend(self):
        self.build()
        self.client.timeline = [state(), state(101), state(103)]
        self.executor.max_wait_frames = 2
        self.assertTrue(self.call().accepted)
        self.assertEqual(self.layer.tick(self.obs), [])
        self.assertEqual(self.layer.progress()[0]["unverified"], 1)
        self.assertEqual(len(self.client.sent), 1)
        self.layer.tick(self.observer.observe())
        self.assertEqual(len(self.client.sent), 1)
        self.client.timeline.append(state(104, [event(frame=104, cell=(1, 1))]))
        self.client.advance()
        self.layer.tick(self.observer.poll())
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(len(self.client.sent), 1)

    def test_unknown_dll_versions_hide_card_and_reject_without_io(self):
        for version in (0, 2):
            with self.subTest(version=version):
                self.build(state(version=version))
                self.assertEqual(self.commander.tactics(), ())
                result = self.call()
                self.assertFalse(result.accepted)
                self.assertIn("guard_v1", result.error)
                with self.assertRaises(TacticDenied):
                    self.registry.run("native_guard", observation=self.obs,
                                      subject=self.pool(), frame=100)
                self.assertEqual(self.client.sent, [])

    def test_missing_map_empty_units_and_bad_parameters_rejected(self):
        self.build()
        for kwargs in ({"units": ()}, {"params": {"cell": [1]}},
                       {"params": {"cell": [True, 2]}},
                       {"params": {"target": self.agent}},
                       {"observation": replace(self.obs, map_data=None)}):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(self.call(**kwargs).accepted)
        self.assertEqual(self.client.sent, [])

    def test_unavailable_actor_rejected_by_l0_before_send(self):
        # Commander 的条件使用全池；具体对象错误在 L0 拒绝并结算为 failed。
        for changes in (dict(native_id=None), dict(native_id=0),
                        dict(object_type=AbstractType.INFANTRY),
                        dict(deploying=True)):
            with self.subTest(changes=changes):
                self.build(state(**changes))
                self.assertTrue(self.call().accepted)
                self.layer.tick(self.obs)
                self.assertEqual(self.client.sent, [])
                self.assertEqual(self.layer.completed[-1]["failed"], [self.agent])

    def test_multiple_vehicles_are_not_partially_submitted(self):
        first = state()
        second = replace(first.objects[0], pointer=TANK+1, native_id=NATIVE_ID+1)
        self.build(replace(first, objects=(*first.objects, second)))
        agents = self.pool().agents()
        self.assertTrue(self.call(units=agents).accepted)
        self.layer.tick(self.obs)
        self.assertEqual(self.client.sent, [])
        self.assertEqual(set(self.layer.completed[-1]["failed"]), set(agents))

    def test_cancel_before_dispatch_only_releases_lease(self):
        self.build()
        accepted = self.call()
        self.assertTrue(self.layer.cancel(accepted.intent_id))
        self.layer.tick(self.obs)
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.layer.squads(), ())

    def test_existing_guard_area_keeps_its_own_parameters(self):
        info = TacticRegistry().load_builtin().get("guard_area").info
        self.assertEqual([p.name for p in info.params], ["radius", "max_frames"])
        self.assertNotIn("guard_v1", info.requires)


class TestHarvestMigration(GuardTacticCase):
    def test_named_cmin_uses_native_guard_through_commander(self):
        initial = miner_state()
        self.build(initial, miner_state(101, mission=Mission.AREA_GUARD,
                                       events=[event(cell=(1, 1))]), names=("harvest",))
        self.assertTrue(self.call("harvest").accepted)
        outcomes = self.layer.tick(self.obs)
        self.assertEqual(outcomes[0].kind, "guard_current")
        self.assertEqual(outcomes[0].evidence, "native_input_observed")
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(len(self.client.sent), 1)

    def test_v1_missing_identity_is_not_hidden_by_legacy_fallback(self):
        self.build(miner_state(native_id=None), names=("harvest",))
        self.assertTrue(self.call("harvest").accepted)
        self.layer.tick(self.obs)
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.layer.completed[-1]["failed"], [self.agent])

    def test_legacy_and_unknown_version_keep_move_to_ore(self):
        for version in (0, 2):
            with self.subTest(version=version):
                self.build(miner_state(version=version), names=("harvest",))
                obs = replace(self.obs, map_data=make_map(ore=[(3, 3)]))
                intents = self.registry.run("harvest", observation=obs,
                                            subject=self.pool(obs), frame=100)
                self.assertEqual([i.kind for i in intents], ["move_to"])
                self.assertEqual(intents[0].cell, (3, 3))

    def test_other_harvesters_keep_legacy_path_even_on_v1(self):
        self.build(miner_state(), names=("harvest",))
        catalogue = make_catalogue()
        # 相同类型表显示名指向另一规则条目，保证实际按 Entry.id 选路径。
        catalogue.by_name["Chrono Miner"] = replace(catalogue.by_name["Chrono Miner"], id="HARV")
        obs = replace(self.obs, catalogue=catalogue, map_data=make_map(ore=[(3, 3)]))
        intents = self.registry.run("harvest", observation=obs,
                                    subject=self.pool(obs), frame=100)
        self.assertEqual([i.kind for i in intents], ["move_to"])


class TestAutoHarvestMigration(GuardTacticCase):
    def setUp(self):
        self.build(miner_state(), names=("auto_harvest",))

    def obs_at(self, frame, mission=Mission.STOP, native_id=NATIVE_ID):
        current = miner_state(frame, mission=mission, native_id=native_id)
        self.observer.absorb(current)
        return self.observer.observe()

    def test_missing_state_or_map_is_an_idle_pulse(self):
        for obs in (replace(self.obs, state=None), replace(self.obs, map_data=None)):
            self.assertEqual(self.registry.run("auto_harvest", observation=obs,
                                               subject=self.pool(obs), frame=100), ())

    def test_cooldown_survives_real_automatic_pulses_and_location_changes(self):
        fake = FakeExecutor()
        auto = Autopilot(self.registry, fake)
        auto.run(self.obs, (), self.pool())
        for frame in (160, 220, 699):
            obs = self.obs_at(frame)
            moved = replace(obs.state.objects[0], coordinates=replace(obs.state.objects[0].coordinates,
                                                                     x=640, y=640))
            obs = replace(obs, state=replace(obs.state, objects=(moved,)))
            auto.run(obs, (), self.pool(obs))
        self.assertEqual([i.kind for i in fake.executed], ["guard_current"])
        obs = self.obs_at(759)
        auto.run(obs, (), self.pool(obs))
        self.assertEqual(len(fake.executed), 2, "仍停工且冷却已过才允许恢复")

    def test_native_activity_is_not_overwritten(self):
        for mission in (Mission.AREA_GUARD, Mission.HARVEST, Mission.MOVE,
                        Mission.RETURN, Mission.ENTER, Mission.UNLOAD):
            with self.subTest(mission=mission):
                obs = self.obs_at(160, mission)
                self.assertEqual(self.registry.run("auto_harvest", observation=obs,
                                                   subject=self.pool(obs), frame=160), ())

    def test_unknown_result_is_not_resent_after_cooldown(self):
        fake = TimeoutExecutor()
        auto = Autopilot(self.registry, fake)
        auto.run(self.obs, (), self.pool())
        obs = self.obs_at(760)
        record = auto.run(obs, (), self.pool(obs))[0]
        self.assertIn("先前命令结果未知", record["skipped"])
        self.assertEqual(len(fake.executed), 1)

    def test_excluded_unit_does_not_consume_cooldown(self):
        memo = {}
        self.assertEqual(self.registry.run("auto_harvest", observation=self.obs,
                                           subject=self.pool(excluded=(self.agent,)),
                                           frame=100, memo=memo), ())
        obs = self.obs_at(160)
        intents = self.registry.run("auto_harvest", observation=obs,
                                    subject=self.pool(obs), frame=160, memo=memo)
        self.assertEqual(len(intents), 1)

    def test_new_identity_at_same_pointer_does_not_inherit_cooldown(self):
        memo = {}
        first = self.registry.run("auto_harvest", observation=self.obs,
                                   subject=self.pool(), frame=100, memo=memo)
        obs = self.obs_at(160, native_id=NATIVE_ID+1)
        intents = self.registry.run("auto_harvest", observation=obs,
                                    subject=self.pool(obs), frame=160, memo=memo)
        self.assertEqual(len(intents), 1)
        self.assertNotEqual(first[0].units, intents[0].units)
        self.assertNotIn(self.agent, memo[("auto_harvest", "recent")])

    def test_temporary_limbo_does_not_clear_same_identity_cooldown(self):
        memo = {}
        self.registry.run("auto_harvest", observation=self.obs,
                          subject=self.pool(), frame=100, memo=memo)
        current = miner_state(160, mission=Mission.ENTER)
        current = replace(current, objects=(replace(current.objects[0], in_limbo=True,
                                                     on_map=False),))
        self.observer.absorb(current)
        obs = self.observer.observe()
        self.assertEqual(self.registry.run("auto_harvest", observation=obs,
                                           subject=self.pool(obs), frame=160, memo=memo), ())
        self.assertIn(self.agent, memo[("auto_harvest", "recent")])
        obs = self.obs_at(220)
        self.assertEqual(self.registry.run("auto_harvest", observation=obs,
                                           subject=self.pool(obs), frame=220, memo=memo), ())


if __name__ == "__main__":
    unittest.main()
