"""Attack 功能组：离线身份、两项证据和薄技法；不证明真机效果。"""
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from ra2agent.command import CallRequest, Commander, UnitPool
from ra2agent.constants import AbstractType, Mission, UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.client import Client
from ra2agent.engine.identity import IdentityTable
from ra2agent.engine.native_events import NativeEvent, NativeTarget
from ra2agent.engine.observation import Observer
from ra2agent.engine.proto import fmap, pb_bytes, pb_uint
from ra2agent.engine.state import ActualTarget, GameState, parse_object
from ra2agent.engine.validate import Validator
from ra2agent.errors import InvalidCommand, ProtocolError, Timeout
from ra2agent.runtime.executor import Executor
from ra2agent.runtime.intents import AttackTarget, Intent
from ra2agent.runtime.micro import MicroLayer
from ra2agent.tactics import TacticRegistry
from tests.fixtures import PLAYER_HOUSE, ENEMY_HOUSE, build_game_state
from tests.test_executor import FakeClient, TANK, ENEMY_TANK, make_map, make_state, tank

ROOT = Path(__file__).resolve().parents[1]
ACTOR_ID, TARGET_ID = 1043800, 0xFFFFFE80


def state(frame=100, *, events=(), target_status=2, actor_changes=None,
          target_changes=None, version=1):
    target = parse_object(tank(ENEMY_TANK, (3, 3), house=ENEMY_HOUSE)
                          + pb_uint(23, TARGET_ID))
    target = replace(target, **(target_changes or {}))
    actor = parse_object(tank(TANK, (1, 1)) + pb_uint(21, ACTOR_ID))
    raw = (None if target_status is None else ActualTarget(target_status))
    if target_status == 3:
        raw = ActualTarget(3, NativeTarget(TARGET_ID - 2**32, 52),
                           int(target.object_type), target.pointer)
    actor = replace(actor, **({"actual_target": raw} | (actor_changes or {})))
    return replace(make_state(frame), objects=(actor, target), _native_events=tuple(events),
                   target_observation_version=1, attack_interface_version=version)


def event(frame=101, actor=ACTOR_ID, target=TARGET_ID, mission=Mission.ATTACK,
          rtti=52, house=0, timing=123):
    payload = (pb_bytes(1, pb_uint(1, actor) + pb_uint(2, 52))
               + pb_uint(2, int(mission))
               + pb_bytes(3, pb_uint(1, target - 2**32 if target >= 2**31 else target)
                          + pb_uint(2, rtti)))
    return NativeEvent.parse(pb_uint(2, house) + pb_uint(3, frame) + pb_uint(4, 4)
                             + pb_bytes(8, payload) + pb_uint(19, timing), "out")


class AttackClient(FakeClient):
    def attack_target_order(self, *args):
        self.sent.append(args)
        return self._reply("UnitOrder")


class TestAttackTarget(unittest.TestCase):
    def build(self, *states, **kwargs):
        self.client = AttackClient(states)
        self.identity = IdentityTable()
        self.identity.update(states[0])
        self.agent = self.identity.agent_id(TANK)
        self.target = self.identity.agent_id(ENEMY_TANK)
        self.intent = AttackTarget(units=(self.agent,), target=self.target)
        self.executor = Executor(self.client, self.identity, validator=Validator(make_map()),
                                 sleep=lambda _: self.client.advance(), **kwargs)
        return self.executor.plan(self.intent, states[0])

    def test_schema_transport_and_legacy_absence(self):
        restored = Intent.from_dict(json.loads(json.dumps(AttackTarget(units=(1,), target=2).to_dict())))
        self.assertIsInstance(restored, AttackTarget)
        self.assertEqual(GameState.parse(build_game_state()).attack_interface_version, 0)
        self.assertIsNone(parse_object(pb_uint(10, ENEMY_TANK)).order_target_native_id)
        for blob in (pb_bytes(20, b'x'), pb_uint(20, 1) + pb_uint(20, 1)):
            with self.assertRaises(ProtocolError):
                GameState.parse(build_game_state() + blob)
        for blob in (pb_bytes(23, b'x'), pb_uint(23, 2**32), pb_uint(23, 1) + pb_uint(23, 2)):
            with self.assertRaises(ProtocolError):
                parse_object(blob)
        args = (TANK, ACTOR_ID, PLAYER_HOUSE, 100, ENEMY_TANK, TARGET_ID, ENEMY_HOUSE, 1)
        raw = payloads.attack_target_order(*args)
        self.assertEqual({f: v[0][1] for f, v in fmap(raw).items()},
                         dict(zip((1, 5, 6, 7, 3, 8, 9, 10), args)) | {2: 16})
        self.assertNotIn(4, fmap(raw))
        client = Client()
        client.send_command = Mock()
        client.attack_target_order(*args)
        self.assertEqual(client.send_command.call_args.args[1], raw)
        for i in range(len(args)):
            for bad in (True, -1, 2**32):
                changed = list(args)
                changed[i] = bad
                with self.subTest(i=i, bad=bad), self.assertRaises(InvalidCommand):
                    payloads.attack_target_order(*changed)
        # protoc independently checks our field numbers and signed native bit pattern.
        text = (f"object_addresses: {TANK} action: UNIT_ACTION_PLAYER_ATTACK_TARGET "
                f"expected_native_id: {ACTOR_ID} expected_house: {PLAYER_HOUSE} basis_frame: 100 "
                f"target_object: {ENEMY_TANK} expected_target_native_id: {TARGET_ID} "
                f"expected_target_house: {ENEMY_HOUSE} expected_target_type: ABSTRACT_TYPE_UNIT")
        encoded = subprocess.check_output(["protoc", "-I", str(ROOT / "proto"),
                                           "--encode=ra2yrproto.commands.UnitOrder",
                                           "ra2yrproto/commands_game.proto"], input=text.encode())
        encoded_fields = fmap(encoded)
        from ra2agent.engine.proto import packed_varints
        self.assertEqual(list(packed_varints(encoded_fields.pop(1)[0][1])), [TANK])
        raw_fields = fmap(raw)
        raw_fields.pop(1)
        self.assertEqual(encoded_fields, raw_fields)

    def test_gates_projection_and_pointer_reuse(self):
        for changes in (dict(version=0), dict(version=2),
                        dict(actor_changes={"native_id": None}),
                        dict(actor_changes={"deploying": True}),
                        dict(target_changes={"order_target_native_id": None}),
                        dict(target_changes={"order_target_native_id": 0}),
                        dict(target_changes={"house": PLAYER_HOUSE}),
                        dict(target_changes={"house": 0xDEAD}),
                        dict(target_changes={"in_limbo": True}),
                        dict(target_changes={"on_map": False}),
                        dict(target_changes={"health": 0}),
                        dict(target_changes={"object_type": AbstractType.INFANTRY}),
                        dict(target_changes={"deploying": True})):
            with self.subTest(changes=changes), self.assertRaises(InvalidCommand):
                self.build(state(**changes))
        initial = state(target_status=3)
        plan = self.build(initial)
        self.assertEqual(plan.action, UnitAction.PLAYER_ATTACK_TARGET)
        obs = Observer(self.client, identity=self.identity, map_data=make_map()).observe(initial)
        self.assertIsNone(obs.visible_enemies[0].order_target_native_id)
        self.assertIsNone(obs.own[0].actual_target)
        self.assertEqual(obs.actual_targets[self.agent].agent_id, self.target)
        old = self.target
        reused = state(101, target_changes={"order_target_native_id": TARGET_ID - 1})
        self.identity.update(reused)
        self.assertNotEqual(self.identity.agent_id(ENEMY_TANK), old)
        self.assertFalse(plan.verify(reused))

    def test_freeze_before_observer_refresh_rejects_transformation_and_rebinding(self):
        initial = state()
        for changes in ({"pointer": ENEMY_TANK + 1, "object_type": AbstractType.BUILDING,
                         "order_target_native_id": TARGET_ID - 1},
                        {"type_pointer": 0xABCD}, {"house": PLAYER_HOUSE},
                        {"order_target_native_id": TARGET_ID - 1}):
            self.build(initial)
            fresh = state(101, target_changes=changes)
            observer = Observer(self.client, identity=self.identity, map_data=make_map())
            def refresh():
                observer.absorb(fresh)
                return fresh
            self.executor._read = refresh
            with self.subTest(changes=changes), self.assertRaises(InvalidCommand):
                self.executor.execute(self.intent, initial)
            self.assertEqual(self.client.sent, [])

    def test_both_evidence_and_no_mission_fallback_or_preexisting_input(self):
        initial = state(events=(event(),), target_status=3)
        plan = self.build(initial)
        self.assertFalse(plan.verify(initial))
        self.assertFalse(plan.verify(state(101, events=(event(),), target_status=3)))
        for bad in (dict(actor=ACTOR_ID+1), dict(target=TARGET_ID+1),
                    dict(mission=Mission.GUARD), dict(rtti=11), dict(house=1)):
            plan = self.build(state())
            self.assertFalse(plan.verify(state(101, events=(event(**bad),), target_status=3)))
        for status in (None, 1, 2):
            plan = self.build(state())
            self.assertFalse(plan.verify(state(101, events=(event(),), target_status=status,
                                              actor_changes={"mission": Mission.ATTACK})))
        for preexisting in (False, True):
            baseline = state(target_status=3 if preexisting else 2)
            plan = self.build(baseline)
            self.assertFalse(plan.verify(state(101, events=(event(),))))
            # Input can leave the queue before a matching Target appears.
            self.assertTrue(plan.verify(state(102, target_status=3)))
            self.assertEqual(plan.observations['native_input'], 'observed')
            self.assertEqual(plan.observations['actual_target'],
                             'preexisting_match' if preexisting else 'state_changed')
        plan = self.build(state())
        wrong = ActualTarget(3, NativeTarget(TARGET_ID - 1, 52), 1, ENEMY_TANK)
        self.assertFalse(plan.verify(state(101, events=(event(),), actor_changes={"actual_target": wrong})))

    def test_execute_one_submission_and_unknown_retains_plan(self):
        initial = state()
        self.build(initial, state(101, events=(event(),)), state(102, target_status=3))
        outcome = self.executor.execute(self.intent, initial)
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(outcome.evidence, 'native_input_and_target_observed')
        self.assertEqual(outcome.observations['actual_target'], 'state_changed')
        self.build(initial, state(101, events=(event(),)), state(103), max_wait_frames=2)
        with self.assertRaises(Timeout) as caught:
            self.executor.execute(self.intent, initial)
        self.assertEqual(len(self.client.sent), 1)
        plan = caught.exception.plan
        self.assertEqual(plan.observations['native_input'], 'observed')
        self.assertFalse(plan.verify(state(104)))
        self.assertTrue(plan.verify(state(105, target_status=3)))
        self.assertEqual(len(self.client.sent), 1)


def candidate():
    from ra2agent.tactics.builtin import attack_target
    return attack_target


class TestAttackTactic(unittest.TestCase):
    def build(self, *states, max_wait_frames=45):
        self.client = AttackClient(states or (state(), state(101, events=(event(),), target_status=3)))
        self.observer = Observer(self.client, map_data=make_map())
        self.obs = self.observer.poll()
        self.agent = self.observer.identity.agent_id(TANK)
        self.target = self.observer.identity.agent_id(ENEMY_TANK)
        self.registry = TacticRegistry().load(candidate().TACTICS)
        self.executor = Executor(self.client, self.observer.identity,
                                 validator=Validator(self.observer.map_data),
                                 read_state=lambda: self.observer.poll().state,
                                 sleep=lambda _: self.client.advance(), max_wait_frames=max_wait_frames)
        self.layer = MicroLayer(self.observer, registry=self.registry, executor=self.executor)
        self.commander = Commander(self.layer, self.observer)
        self.request = CallRequest(tactic='attack_target', units=(self.agent,), params={'target': self.target})

    def test_pool_call_scope_single_settlement_and_release(self):
        self.build()
        intents = self.registry.run('attack_target', observation=self.obs,
                                    subject=UnitPool(self.obs, self.observer.identity),
                                    params={'target': self.target}, frame=100)
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].scope.objects, (self.agent,))
        self.assertEqual(intents[0].target, self.target)
        accepted = self.commander.call([self.request], self.obs)[0]
        self.assertTrue(accepted.accepted, accepted.error)
        self.assertEqual(self.layer.tick(self.obs)[0].observations['native_input'], 'observed')
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(self.layer.completed[-1]['completion_basis'], {self.agent: 'operation_observed'})
        report = self.commander.status(self.observer.poll())
        text = report.render()
        self.assertIn('operation_observed', text)
        self.assertIn('native_input=observed', text)
        self.assertIn('actual_target=state_changed', text)
        self.assertIn('native_input_and_target_observed', text)
        self.assertEqual(report.units[0]['actual_target'],
                         {'status': 'object', 'agent_id': self.target})
        self.assertNotIn(str(ACTOR_ID), text)
        self.assertEqual(self.commander.status(self.observer.poll()).results, ())
        self.layer.tick(self.observer.poll())
        self.assertEqual(len(self.client.sent), 1)

    def test_unknown_late_match_and_cancel_never_send_stop(self):
        for cancel in (False, True):
            self.build(state(), state(101, events=(event(),)), state(103), max_wait_frames=2)
            accepted = self.commander.call([self.request], self.obs)[0]
            self.assertTrue(accepted.accepted)
            self.assertEqual(self.layer.tick(self.obs), [])
            self.layer.tick(self.observer.poll())
            self.assertEqual(len(self.client.sent), 1)
            if cancel:
                self.assertTrue(self.layer.cancel(accepted.intent_id))
            text = self.commander.status(self.observer.poll()).render()
            self.assertIn('结果未知', text)
            self.assertNotIn('operation_observed', text)
            self.client.timeline.append(state(104, target_status=3))
            self.client.advance()
            self.layer.tick(self.observer.poll())
            self.assertEqual(self.layer.squads(), ())
            self.assertEqual(len(self.client.sent), 1)

    def test_unsupported_missing_parameter_empty_units_and_no_map(self):
        for states in ((state(version=0),), (state(version=2),)):
            self.build(*states)
            self.assertFalse(self.commander.call([self.request], self.obs)[0].accepted)
        self.build()
        for request, obs in ((replace(self.request, units=()), self.obs),
                             (replace(self.request, params={}), self.obs),
                             (replace(self.request, params={'target': True}), self.obs),
                             (self.request, replace(self.obs, map_data=None))):
            self.assertFalse(self.commander.call([request], obs)[0].accepted)
        self.assertEqual(self.client.sent, [])


class TestAttackNativePolicy(unittest.TestCase):
    def test_compiled_policy_rejects_identity_legality_and_dynamic_changes(self):
        patch = (ROOT / 'engine/ra2yrcpp/patches/attack-v1-engine.patch').read_text()
        section = patch.split('diff --git a/src/ra2/attack_policy.hpp b/src/ra2/attack_policy.hpp\n', 1)[1]
        section = section.split('\ndiff --git ', 1)[0]
        header = '\n'.join(line[1:] for line in section.splitlines()
                           if line.startswith('+') and not line.startswith('+++')) + '\n'
        with tempfile.TemporaryDirectory(prefix='ra2-attack-policy-') as directory:
            root = Path(directory)
            (root/'attack_policy.hpp').write_text(header)
            (root/'check.cpp').write_text('''#include "attack_policy.hpp"
#include <cassert>
int main() {
  using namespace ra2::attack_policy;
  Target base{0xFFFFFE80u, 8192, 1, true, true, true, false};
  assert(matches(base, 0xFFFFFE80u, 8192, 1));
  auto building = base; building.type = 6;
  assert(matches(building, base.native_id, base.house, 6));
  Target cases[] = {{0,8192,1,true,true,true,false}, {1,0,1,true,true,true,false},
                   {1,8192,2,true,true,true,false}, {1,8192,1,false,true,true,false},
                   {1,8192,1,true,false,true,false}, {1,8192,1,true,true,false,false},
                   {1,8192,1,true,true,true,true}};
  for (auto t : cases) assert(!eligible(t));
  assert(!matches(base, base.native_id-1, base.house, base.type));
  assert(!matches(base, base.native_id, base.house+1, base.type));
  assert(!matches(base, base.native_id, base.house, 6));
}
''')
            subprocess.run(['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            str(root/'check.cpp'), '-o', str(root/'check')], check=True,
                           capture_output=True, text=True)
            subprocess.run([str(root/'check')], check=True)


if __name__ == '__main__':
    unittest.main()
