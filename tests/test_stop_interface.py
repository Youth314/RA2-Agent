"""Stop/Idle 离线契约；合成输入不证明玩家效果或已加载 DLL。"""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from ra2agent.command import CallRequest, Commander, UnitPool
from ra2agent.constants import AbstractType, Mission, UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.client import Client
from ra2agent.engine.identity import IdentityTable
from ra2agent.engine.native_events import NativeEvent
from ra2agent.engine.observation import Observer
from ra2agent.engine.proto import fmap, pb_bytes, pb_uint
from ra2agent.engine.state import GameState
from ra2agent.engine.validate import Validator
from ra2agent.errors import InvalidCommand, ProtocolError, TacticDenied, Timeout
from ra2agent.runtime.executor import Executor
from ra2agent.runtime.intents import Hold, Intent, Stop
from ra2agent.runtime.micro import MicroLayer
from ra2agent.tactics import Mode, Tactic, TacticInfo, TacticRegistry
from tests.fixtures import ENEMY_HOUSE, build_game_state
from tests.test_executor import FakeClient, TANK, make_map
from tests.test_guard_interface import NATIVE_ID, state as guard_state


def state(frame=100, events=(), version=1, **changes):
    return replace(guard_state(frame, events, **changes), stop_interface_version=version)


def event(frame=101, actor=NATIVE_ID, rtti=52, house=0, timing=123,
          event_type=6, source="out", missing=False):
    whom = pb_uint(1, actor) + pb_uint(2, rtti)
    raw = (pb_uint(2, house) + pb_uint(3, frame) + pb_uint(4, event_type)
           + pb_uint(19, timing))
    if not missing:
        raw += pb_bytes(7, pb_bytes(1, whom))
    return NativeEvent.parse(raw, source)


class StopClient(FakeClient):
    def stop_order(self, pointer, native_id, house_pointer, basis_frame):
        self.sent.append((pointer, native_id, house_pointer, basis_frame))
        return self._reply("UnitOrder")


class TestStopInterface(unittest.TestCase):
    def build(self, *states, **options):
        self.client = StopClient(states)
        self.identity = IdentityTable()
        self.identity.update(states[0])
        self.agent = self.identity.agent_id(TANK)
        self.intent = Stop(units=(self.agent,))
        self.executor = Executor(self.client, self.identity, validator=Validator(make_map()),
                                 sleep=lambda _: self.client.advance(), **options)
        return self.executor.plan(self.intent, states[0])

    def test_real_manual_and_interface_idle_samples(self):
        fixture = json.loads((Path(__file__).parent / 'data/stop_native.json').read_text())
        self.assertEqual({s['label'] for s in fixture['samples']}, {'manual', 'moving', 'stationary'})
        for sample in fixture['samples']:
            native = NativeEvent.parse(bytes.fromhex(sample['raw_hex']), sample['source'])
            self.assertEqual(native.event_type, 6)
            self.assertEqual(native.idle_actor.m_id, sample['native_id'])
            self.assertEqual(native.idle_actor.m_rtti, 52)
            initial = state(sample['observed_frame']-2, native_id=sample['native_id'])
            initial = replace(initial, houses=tuple(replace(h, array_index=1) for h in initial.houses))
            plan = self.build(initial)
            observed = replace(initial, frame=sample['observed_frame'], _native_events=(native,))
            self.assertTrue(plan.verify(observed))
            self.assertFalse(plan.verify(replace(observed, _native_events=())))

    def test_protocol_and_roundtrip(self):
        original = Stop(units=(1,))
        restored = Intent.from_dict(json.loads(json.dumps(original.to_dict())))
        self.assertIsInstance(restored, Stop)
        self.assertEqual(tuple(restored.units), (1,))
        self.assertEqual(GameState.parse(build_game_state()).stop_interface_version, 0)
        self.assertEqual(GameState.parse(build_game_state()+pb_uint(18, 1)).stop_interface_version, 1)
        with self.assertRaises(ProtocolError):
            GameState.parse(build_game_state()+pb_bytes(18, b'x'))
        raw = payloads.stop_order(TANK, NATIVE_ID, 123, 100)
        fields = fmap(raw)
        self.assertEqual(fields, {1: [(0, TANK)], 2: [(0, 15)], 5: [(0, NATIVE_ID)],
                                  6: [(0, 123)], 7: [(0, 100)]})
        client = Client()
        client.send_command = Mock()
        client.stop_order(TANK, NATIVE_ID, 123, 100)
        self.assertEqual(client.send_command.call_args.args[1], raw)
        for index in range(4):
            for bad in (True, -1, 2**32):
                args = [TANK, NATIVE_ID, 123, 100]
                args[index] = bad
                with self.assertRaises(InvalidCommand):
                    payloads.stop_order(*args)

    def test_idle_only_and_missing_payload(self):
        self.assertEqual(event().idle_actor.m_id, NATIVE_ID)
        self.assertIsNone(event(event_type=4).idle_actor)
        self.assertIsNone(event(missing=True).idle_actor)
        # Wrong wire type is rejected only for the active payload.
        bad = pb_uint(4, 6)+pb_uint(7, 1)
        with self.assertRaises(ProtocolError):
            NativeEvent.parse(bad, 'out')
        self.assertIsNone(NativeEvent.parse(pb_uint(4, 4)+pb_uint(7, 1), 'out').idle_actor)
        with self.assertRaises(ProtocolError):
            NativeEvent.parse(pb_uint(4, 6)+pb_bytes(7, pb_uint(1, 1)), 'out')

    def test_gate_and_legacy_action_is_not_used(self):
        for changes in (dict(version=0), dict(version=2), dict(native_id=None),
                        dict(native_id=0), dict(house=ENEMY_HOUSE), dict(health=0),
                        dict(on_map=False), dict(in_limbo=True), dict(deploying=True),
                        dict(undeploying=True), dict(object_type=AbstractType.INFANTRY),
                        dict(object_type=AbstractType.BUILDING)):
            with self.subTest(changes=changes), self.assertRaises(InvalidCommand):
                self.build(state(**changes))
            self.assertEqual(self.client.sent, [])
        plan = self.build(replace(state(), guard_interface_version=0))
        self.assertEqual(plan.action, UnitAction.PLAYER_STOP)
        self.assertNotEqual(plan.action, UnitAction.STOP)
        self.assertIsNone(plan.coordinates)
        self.assertEqual(self.client.state_calls, 0)
        for units in ((), (self.agent, self.agent)):
            with self.assertRaises(InvalidCommand):
                self.executor.plan(Stop(units=units), state())
        with self.assertRaises(InvalidCommand):
            Validator(make_map(), allow_foreign=True).check_stop(state(house=ENEMY_HOUSE), (TANK,))

    def test_receipt_requires_new_idle_actor_not_mission(self):
        plan = self.build(state(mission=Mission.GUARD))
        for mission in (Mission.STOP, Mission.GUARD, Mission.MOVE):
            self.assertFalse(plan.verify(state(101, mission=mission)))
            self.assertTrue(plan.verify(state(101, [event()], mission=mission)))
        for changes in (dict(actor=NATIVE_ID+1), dict(house=1), dict(rtti=0),
                        dict(rtti=11), dict(frame=99), dict(event_type=4), dict(missing=True)):
            with self.subTest(changes=changes):
                self.assertFalse(plan.verify(state(101, [event(**changes)])))
        for changes in (dict(native_id=NATIVE_ID+1), dict(house=ENEMY_HOUSE),
                        dict(in_limbo=True), dict(on_map=False), dict(health=0)):
            self.assertFalse(plan.verify(state(101, [event()], **changes)))

    def test_old_idle_rescheduled_is_not_new(self):
        plan = self.build(state(events=[event(frame=100)]))
        self.assertFalse(plan.verify(state(110, [event(frame=120, source='do')])))
        self.assertTrue(plan.verify(state(110, [event(frame=120, timing=124)])))

    def test_execute_and_identity_refresh(self):
        initial = state()
        self.build(initial, state(101, [event()], mission=Mission.GUARD))
        outcome = self.executor.execute(self.intent, initial)
        self.assertEqual(outcome.evidence, 'native_input_observed')
        self.assertEqual(self.client.sent, [(TANK, NATIVE_ID, initial.player_house().pointer, 100)])
        self.build(initial, state(101, native_id=NATIVE_ID+1))
        self.client.advance()
        with self.assertRaises(InvalidCommand):
            self.executor.execute(self.intent, initial)
        self.assertEqual(self.client.sent, [])

    def test_timeout_unknown_no_retry(self):
        initial = state()
        self.build(initial, state(101), state(103), max_wait_frames=2)
        with self.assertRaises(Timeout) as caught:
            self.executor.execute(self.intent, initial)
        self.assertEqual(caught.exception.plan.verify_basis, 'native_input')
        self.assertEqual(len(self.client.sent), 1)


class TestStopTactic(unittest.TestCase):
    def setup_chain(self, version=1, *, initial=None, halt=False):
        initial = initial if initial is not None else state(version=version)
        self.client = StopClient([initial, state(101, [event()])])
        self.observer = Observer(self.client, map_data=make_map())
        self.observation = self.observer.poll()
        self.agent = self.observer.identity.agent_id(TANK)
        builtin = TacticRegistry().load_builtin()
        names = ('stop', 'halt', 'hold_position') if halt else ('stop',)
        registry = TacticRegistry().load(builtin.get(name) for name in names)
        if halt:
            # 只在测试中暴露组合入口，验证模型 → 组合 → 隐藏零件 → Stop 的完整链。
            def halt_probe(context):
                return context.call('halt')
            registry.register(Tactic(TacticInfo(
                name='halt_probe', summary='测试用单车辆停止组合',
                requires=('has_units', 'has_map', 'stop_v1'),
            ), halt_probe))
        self.registry = registry
        executor = Executor(self.client, self.observer.identity, validator=Validator(make_map()),
                            read_state=lambda: self.observer.poll().state,
                            sleep=lambda _: self.client.advance())
        self.executor = executor
        self.layer = MicroLayer(self.observer, registry=registry, executor=executor)
        self.commander = Commander(self.layer, self.observer)

    def test_call_input_completion_release_and_no_repeat(self):
        self.setup_chain()
        result = self.commander.call([CallRequest(tactic='stop', units=(self.agent,))], self.observation)[0]
        self.assertTrue(result.accepted, result.error)
        outcomes = self.layer.tick(self.observation)
        self.assertEqual(outcomes[0].evidence, 'native_input_observed')
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(self.layer.completed[-1]['completion_basis'], {self.agent: 'operation_observed'})
        self.layer.tick(self.observer.poll())
        self.assertEqual(len(self.client.sent), 1)

    def test_pool_and_unknown_result_lifecycle(self):
        self.setup_chain()
        intents = self.registry.run('stop', observation=self.observation,
                                    subject=UnitPool(self.observation, self.observer.identity), frame=100)
        self.assertEqual(intents[0].units, (self.agent,))
        self.client.timeline = [state(), state(101), state(103)]
        self.executor.max_wait_frames = 2
        request = CallRequest(tactic='stop', units=(self.agent,))
        self.assertTrue(self.commander.call([request], self.observation)[0].accepted)
        self.assertEqual(self.layer.tick(self.observation), [])
        self.assertEqual(self.layer.progress()[0]['unverified'], 1)
        self.layer.tick(self.observer.poll())
        self.assertEqual(len(self.client.sent), 1)
        self.client.timeline.append(state(104, [event(frame=104)]))
        self.client.advance()
        self.layer.tick(self.observer.poll())
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(len(self.client.sent), 1)

    def test_cancel_before_input_does_not_stop(self):
        self.setup_chain()
        accepted = self.commander.call([CallRequest(tactic='stop', units=(self.agent,))], self.observation)[0]
        self.assertTrue(accepted.accepted)
        self.assertTrue(self.layer.cancel(accepted.intent_id))
        self.layer.tick(self.observation)
        self.assertEqual(self.client.sent, [])

    def test_gate_empty_and_no_map(self):
        self.setup_chain(version=0)
        request = CallRequest(tactic='stop', units=(self.agent,))
        self.assertFalse(self.commander.call([request], self.observation)[0].accepted)
        self.setup_chain()
        self.assertFalse(self.commander.call([CallRequest(tactic='stop', units=())], self.observation)[0].accepted)
        self.assertFalse(self.commander.call([request], replace(self.observation, map_data=None))[0].accepted)
        self.assertEqual(self.client.sent, [])

    def test_halt_pool_and_composite_confirm_input_and_release(self):
        self.setup_chain(halt=True)
        pool = UnitPool(self.observation, self.observer.identity)
        intents = self.registry.run('halt', observation=self.observation,
                                    subject=pool, frame=100)
        self.assertEqual(len(intents), 1)
        self.assertIsInstance(intents[0], Stop)
        self.assertEqual(intents[0].units, (self.agent,))
        self.assertEqual(intents[0].created_frame, 100)
        self.assertEqual(intents[0].scope.objects, (self.agent,))
        accepted = self.commander.call([
            CallRequest(tactic='halt_probe', units=(self.agent,))], self.observation)[0]
        self.assertTrue(accepted.accepted, accepted.error)
        self.assertEqual(self.layer.tick(self.observation)[0].evidence, 'native_input_observed')
        self.assertEqual(self.layer.completed[-1]['completion_basis'],
                         {self.agent: 'operation_observed'})
        self.assertEqual(self.layer.squads(), ())
        self.layer.tick(self.observer.poll())
        self.assertFalse(self.layer.cancel(accepted.intent_id))
        self.assertEqual(self.client.sent,
                         [(TANK, NATIVE_ID, self.observation.house.pointer, 100)])

    def test_halt_is_hidden_and_old_or_unknown_versions_do_not_fallback(self):
        for version in (0, 1, 2):
            with self.subTest(version=version):
                self.setup_chain(version, halt=True)
                self.assertNotIn('halt', [card.name for card in self.registry.cards(Mode.MATCH)])
                self.assertFalse(self.commander.call([
                    CallRequest(tactic='halt', units=(self.agent,))], self.observation)[0].accepted)
                if version != 1:
                    with self.assertRaises(TacticDenied):
                        self.registry.run('halt', observation=self.observation,
                                          subject=UnitPool(self.observation, self.observer.identity))
                self.assertEqual(self.client.sent, [])
        with self.assertRaises(TacticDenied):
            self.registry.run('halt', observation=replace(self.observation, map_data=None),
                              subject=UnitPool(self.observation, self.observer.identity))

    def test_halt_does_not_bypass_disabled_stop(self):
        self.setup_chain(halt=True)
        self.registry.policy.disabled = frozenset({'stop'})
        with self.assertRaises(TacticDenied):
            self.registry.run('halt', observation=self.observation,
                              subject=UnitPool(self.observation, self.observer.identity))
        accepted = self.commander.call([
            CallRequest(tactic='halt_probe', units=(self.agent,))], self.observation)[0]
        self.assertTrue(accepted.accepted, accepted.error)
        self.layer.tick(self.observation)
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.layer.completed, [])
        self.assertEqual(self.layer.progress()[0]['unverified'], 0)
        self.assertTrue(self.layer.cancel(accepted.intent_id))
        self.assertEqual(self.client.sent, [])

    def test_halt_invalid_actor_or_batch_never_submits_legacy_stop(self):
        first = state()
        second = replace(first.objects[0], pointer=TANK+1, native_id=NATIVE_ID+1)
        for initial in (state(object_type=AbstractType.INFANTRY), state(native_id=None),
                        state(deploying=True), replace(first, objects=(*first.objects, second))):
            with self.subTest(initial=initial):
                self.setup_chain(initial=initial, halt=True)
                units = UnitPool(self.observation, self.observer.identity).agents()
                accepted = self.commander.call([
                    CallRequest(tactic='halt_probe', units=units)], self.observation)[0]
                self.assertTrue(accepted.accepted, accepted.error)
                self.layer.tick(self.observation)
                self.assertEqual(self.client.sent, [])
                self.assertEqual(set(self.layer.completed[-1]['failed']), set(units))

    def test_halt_unknown_result_keeps_lease_and_does_not_resend(self):
        self.setup_chain(halt=True)
        self.client.timeline = [state(), state(101), state(103)]
        self.executor.max_wait_frames = 2
        accepted = self.commander.call([
            CallRequest(tactic='halt_probe', units=(self.agent,))], self.observation)[0]
        self.assertTrue(accepted.accepted, accepted.error)
        self.assertEqual(self.layer.tick(self.observation), [])
        self.assertEqual(self.layer.progress()[0]['unverified'], 1)
        self.layer.tick(self.observer.poll())
        self.assertEqual(len(self.client.sent), 1)
        self.client.timeline.append(state(104, [event(frame=104)]))
        self.client.advance()
        self.layer.tick(self.observer.poll())
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(len(self.client.sent), 1)

    def test_halt_cancel_before_input_does_not_send_stop(self):
        self.setup_chain(halt=True)
        accepted = self.commander.call([
            CallRequest(tactic='halt_probe', units=(self.agent,))], self.observation)[0]
        self.assertTrue(accepted.accepted, accepted.error)
        self.assertTrue(self.layer.cancel(accepted.intent_id))
        self.layer.tick(self.observation)
        self.assertEqual(self.client.sent, [])

    def test_hold_position_keeps_legacy_batch_on_both_dll_versions(self):
        for version in (0, 1):
            with self.subTest(version=version):
                first = state(version=version)
                second = replace(first.objects[0], pointer=TANK+1, native_id=NATIVE_ID+1)
                initial = replace(first, objects=(*first.objects, second))
                self.setup_chain(initial=initial, halt=True)
                pool = UnitPool(self.observation, self.observer.identity)
                intents = self.registry.run('hold_position', observation=self.observation,
                                            subject=pool, frame=100)
                self.assertEqual(len(intents), 1)
                self.assertIsInstance(intents[0], Hold)
                self.assertEqual(intents[0].units, pool.agents())
                self.assertEqual(self.executor.plan(intents[0], initial).action, UnitAction.STOP)
                self.assertEqual(self.client.sent, [])


if __name__ == '__main__':
    unittest.main()
