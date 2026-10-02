"""Guard v1 的离线边界；不证明原版操作等价或游戏内生效。"""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from ra2agent.constants import AbstractType, Mission, UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.client import Client
from ra2agent.engine.identity import IdentityTable
from ra2agent.engine.observation import Observer
from ra2agent.engine.native_events import NativeEvent
from ra2agent.engine.proto import fmap, pb_bytes, pb_uint
from ra2agent.engine.state import GameState, cell_center, parse_object
from ra2agent.engine.validate import Validator
from ra2agent.errors import InvalidCommand, ProtocolError, Timeout
from ra2agent.runtime.executor import Executor
from ra2agent.runtime.intents import GuardCurrent, GuardPosition, Intent
from ra2agent.runtime.micro import MicroLayer
from ra2agent.command import CallRequest, Commander, UnitPool
from ra2agent.tactics import REQUIRED, Param, Tactic, TacticInfo, TacticRegistry, is_cell
from tests.guard_probe_tactics import guard_current, guard_position
from tests.fixtures import ENEMY_HOUSE, build_game_state
from tests.test_executor import FakeClient, TANK, make_map, make_state, tank

NATIVE_ID = 1043820


def state(frame=100, events=(), version=1, **changes):
    obj = parse_object(tank(TANK, (1, 1)) + pb_uint(21, NATIVE_ID))
    obj = replace(obj, **changes)
    return replace(make_state(frame), objects=(obj,),
                   guard_interface_version=version, _native_events=tuple(events))


def event(frame=101, cell=(2, 2), actor=NATIVE_ID, mission=11,
          house=0, source="out", event_type=4, executed=False, timing=123):
    target = pb_uint(1, cell[0] + 1000 * cell[1]) + pb_uint(2, 11)
    whom = pb_uint(1, actor) + pb_uint(2, 52)
    mega = pb_bytes(1, whom) + pb_uint(2, mission) + pb_bytes(3, target)
    raw = (pb_uint(1, int(executed)) + pb_uint(2, house)
           + pb_uint(3, frame) + pb_uint(4, event_type) + pb_bytes(8, mega)
           + pb_uint(19, timing))
    return NativeEvent.parse(raw, source)


class GuardClient(FakeClient):
    def guard_order(self, pointer, action, native_id, house_pointer,
                    basis_frame, coordinates=None):
        self.sent.append((pointer, action, native_id, house_pointer,
                          basis_frame, coordinates))
        return self._reply("UnitOrder")


class GuardCase(unittest.TestCase):
    def build(self, *states, **options):
        self.client = GuardClient(states)
        self.identity = IdentityTable()
        self.identity.update(states[0])
        self.agent = self.identity.agent_id(TANK)
        self.executor = Executor(self.client, self.identity,
                                 validator=Validator(make_map()),
                                 sleep=lambda _: self.client.advance(), **options)
        return self.executor

    def intent(self, cell=None):
        if cell is None:
            return GuardCurrent(units=(self.agent,))
        return GuardPosition(units=(self.agent,), cell=cell)


class TestGuardProtocol(unittest.TestCase):
    def test_real_inputs_match_native_identity_and_cell_readback(self):
        fixture = json.loads((Path(__file__).parent / "data/guard_interface_native.json").read_text())
        self.assertEqual(len(fixture["samples"]), 3)
        for sample in fixture["samples"]:
            with self.subTest(label=sample["label"]):
                obj = parse_object(bytes.fromhex(sample["object_hex"]))
                native = NativeEvent.parse(bytes.fromhex(sample["event_hex"]), sample["source"])
                self.assertEqual(obj.native_id, sample["native_id"])
                self.assertEqual(native.mega_mission.whom.m_id, obj.native_id)
                self.assertEqual(native.mega_mission.whom.m_rtti, 52)
                self.assertEqual(native.mega_mission.mission, Mission.AREA_GUARD)
                self.assertEqual(native.mega_mission.target.cell, tuple(sample["target_cell"]))
                self.assertTrue(native.mega_mission.destination.is_null)
                self.assertGreaterEqual(native.frame, sample["submitted_frame"])
                if "rescheduled_event_hex" in sample:
                    later = NativeEvent.parse(bytes.fromhex(sample["rescheduled_event_hex"]),
                                              sample["rescheduled_source"])
                    self.assertNotEqual(later.frame, native.frame)
                    self.assertEqual(later.timing, native.timing)
                    self.assertEqual(later.mega_mission, native.mega_mission)

    def test_intents_survive_json_round_trip(self):
        for original in (GuardCurrent(units=(1,)), GuardPosition(units=(1,), cell=(2, 3))):
            restored = Intent.from_dict(json.loads(json.dumps(original.to_dict())))
            self.assertEqual(type(restored), type(original))
            self.assertEqual(tuple(restored.units), original.units)
            if isinstance(restored, GuardPosition):
                self.assertEqual(tuple(restored.cell), original.cell)

    def test_client_uses_controlled_unit_order_payload(self):
        client = Client()
        client.send_command = Mock()
        client.guard_order(TANK, UnitAction.GUARD_CURRENT, NATIVE_ID, 123, 100)
        args = client.send_command.call_args.args
        self.assertTrue(args[0].endswith("UnitOrder"))
        self.assertEqual(args[1], payloads.guard_order(TANK, UnitAction.GUARD_CURRENT,
                                                     NATIVE_ID, 123, 100))

    def test_legacy_has_no_capability_or_identity(self):
        self.assertEqual(GameState.parse(build_game_state()).guard_interface_version, 0)
        self.assertIsNone(parse_object(tank(TANK, (1, 1))).native_id)

    def test_extensions_and_zero_presence(self):
        self.assertEqual(GameState.parse(build_game_state() + pb_uint(17, 1))
                         .guard_interface_version, 1)
        self.assertEqual(parse_object(tank(TANK, (1, 1)) + pb_uint(21, 0)).native_id, 0)

    def test_malformed_extensions_fail(self):
        for extension in (pb_bytes(21, b"x"), pb_uint(21, 2**32)):
            with self.subTest(extension=extension), self.assertRaises(ProtocolError):
                parse_object(tank(TANK, (1, 1)) + extension)
        with self.assertRaises(ProtocolError):
            GameState.parse(build_game_state() + pb_bytes(17, b"x"))

    def test_payload_fields(self):
        raw = payloads.guard_order(TANK, UnitAction.GUARD_POSITION, NATIVE_ID,
                                   123, 100, cell_center(2, 3))
        fields = fmap(raw)
        self.assertEqual(fields[1], [(0, TANK)])
        for number, value in ((2, 14), (5, NATIVE_ID), (6, 123), (7, 100)):
            self.assertEqual(fields[number], [(0, value)])
        self.assertNotIn(3, fields)
        self.assertIn(4, fields)

    def test_payload_rejects_wrong_action_identity_and_shape(self):
        base = dict(pointer=TANK, action=UnitAction.GUARD_CURRENT,
                    native_id=NATIVE_ID, house_pointer=123, basis_frame=100)
        cases = [dict(action=UnitAction.MOVE), dict(pointer=0), dict(native_id=0),
                 dict(native_id=2**32), dict(house_pointer=True),
                 dict(basis_frame=-1), dict(action=UnitAction.GUARD_POSITION),
                 dict(coordinates=cell_center(1, 1))]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(InvalidCommand):
                payloads.guard_order(**(base | changes))


class TestGuardValidation(GuardCase):
    def test_supported_plan_has_no_io(self):
        initial = state()
        self.build(initial)
        plan = self.executor.plan(self.intent(), initial)
        self.assertEqual(plan.action, UnitAction.GUARD_CURRENT)
        self.assertIsNone(plan.coordinates)
        self.assertEqual(plan.native_id, NATIVE_ID)
        self.assertEqual(plan.basis_frame, 100)
        self.assertEqual(plan.verify_basis, "native_input")
        self.assertEqual(self.client.state_calls, 0)
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.executor.plan(self.intent((2, 3)), initial).coordinates,
                         cell_center(2, 3))

    def test_unsupported_or_unavailable_actor(self):
        cases = [dict(version=0), dict(version=2), dict(native_id=None),
                 dict(native_id=0), dict(house=ENEMY_HOUSE), dict(health=0),
                 dict(on_map=False), dict(in_limbo=True), dict(deploying=True),
                 dict(undeploying=True), dict(object_type=AbstractType.INFANTRY),
                 dict(object_type=AbstractType.BUILDING)]
        for changes in cases:
            with self.subTest(changes=changes):
                initial = state(**changes)
                self.build(initial)
                with self.assertRaises(InvalidCommand):
                    self.executor.plan(self.intent(), initial)

    def test_foreign_permission_cannot_override_guard(self):
        initial = state(house=ENEMY_HOUSE)
        with self.assertRaises(InvalidCommand):
            Validator(make_map(), allow_foreign=True).check_guard(initial, (TANK,))

    def test_actor_count_and_cell_shape(self):
        initial = state()
        self.build(initial)
        for units in ((), (self.agent, self.agent)):
            with self.assertRaises(InvalidCommand):
                self.executor.plan(GuardCurrent(units=units), initial)
        for cell in ((-1, 2), (8, 2), (2,), (True, 2), (2.1, 2)):
            with self.subTest(cell=cell), self.assertRaises(InvalidCommand):
                self.executor.plan(self.intent(cell), initial)


class TestGuardReceipt(GuardCase):
    def test_old_mission_or_destination_is_not_confirmation(self):
        initial = state(mission=Mission.AREA_GUARD, destination=cell_center(2, 2))
        self.build(initial)
        self.assertFalse(self.executor.plan(self.intent((2, 2)), initial).verify(initial))

    def test_new_input_matches_current_or_exact_position(self):
        initial = state()
        self.build(initial)
        current = self.executor.plan(self.intent(), initial)
        position = self.executor.plan(self.intent((2, 2)), initial)
        self.assertTrue(current.verify(state(101, [event(cell=(3, 3))])))
        self.assertTrue(position.verify(state(101, [event()])))
        self.assertFalse(position.verify(state(101, [event(cell=(3, 3))])))

    def test_wrong_input_or_changed_actor_does_not_match(self):
        initial = state()
        self.build(initial)
        plan = self.executor.plan(self.intent(), initial)
        for changes in (dict(frame=99), dict(actor=NATIVE_ID+1), dict(mission=1),
                        dict(house=1), dict(cell=(9, 9)), dict(event_type=6)):
            with self.subTest(changes=changes):
                self.assertFalse(plan.verify(state(101, [event(**changes)])))
        for changes in (dict(native_id=NATIVE_ID+1), dict(in_limbo=True),
                        dict(house=ENEMY_HOUSE)):
            self.assertFalse(plan.verify(state(101, [event()], **changes)))

    def test_old_input_moving_from_out_to_do_is_not_new(self):
        initial = state(events=[event(frame=100)])
        self.build(initial)
        plan = self.executor.plan(self.intent(), initial)
        later = state(101, [event(frame=100, source="do", executed=True)])
        self.assertFalse(plan.verify(later))

    def test_old_input_rescheduled_to_a_future_frame_is_not_new(self):
        initial = state(events=[event(frame=100)])
        self.build(initial)
        plan = self.executor.plan(self.intent(), initial)
        self.assertFalse(plan.verify(state(110, [event(frame=120, source="do", executed=True)])))
        self.assertTrue(plan.verify(state(110, [event(frame=120, timing=124)])))

    def test_execute_reports_input_evidence(self):
        initial = state()
        self.build(initial, state(101, [event()]))
        outcome = self.executor.execute(self.intent(), initial)
        self.assertEqual(outcome.evidence, "native_input_observed")
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(self.client.sent[0][2:5],
                         (NATIVE_ID, initial.player_house().pointer, 100))

    def test_timeout_retains_unknown_result_without_retry(self):
        initial = state()
        self.build(initial, state(101), state(103), max_wait_frames=2)
        with self.assertRaises(Timeout) as caught:
            self.executor.execute(self.intent(), initial)
        self.assertEqual(caught.exception.plan.verify_basis, "native_input")
        self.assertEqual(len(self.client.sent), 1)

    def test_reused_pointer_before_execution_rejects_old_agent_id(self):
        initial = state()
        self.build(initial, state(101, native_id=NATIVE_ID+1))
        self.client.advance()
        with self.assertRaises(InvalidCommand):
            self.executor.execute(self.intent(), initial)
        self.assertEqual(self.client.sent, [])
        self.assertIsNone(self.identity.pointer_of(self.agent))


class TestNativeIdentity(unittest.TestCase):
    def test_transformation_keeps_agent_id_and_replaces_native_id(self):
        table = IdentityTable()
        table.update(state())
        old = table.agent_id(TANK)
        delta = table.update(state(101, pointer=TANK+1, native_id=NATIVE_ID+1,
                                  object_type=AbstractType.BUILDING))
        self.assertEqual(delta.transformed, [(old, TANK+1)])
        self.assertEqual(table.tracked(old).native_id, NATIVE_ID+1)

    def test_reuse_creates_new_identity(self):
        table = IdentityTable()
        table.update(state())
        old = table.agent_id(TANK)
        delta = table.update(state(101, native_id=NATIVE_ID+1))
        self.assertEqual(delta.vanished, [old])
        self.assertEqual(delta.appeared, [table.agent_id(TANK)])
        self.assertNotEqual(table.agent_id(TANK), old)

    def test_missing_optional_id_does_not_erase_known_identity(self):
        table = IdentityTable()
        table.update(state())
        old = table.agent_id(TANK)
        table.update(state(101, native_id=None))
        self.assertEqual(table.tracked(old).native_id, NATIVE_ID)
        table.update(state(102, native_id=NATIVE_ID+1))
        self.assertIsNone(table.pointer_of(old))


class TestGuardTacticIntegration(unittest.TestCase):
    def setUp(self):
        self.initial = state()
        self.client = GuardClient([self.initial, state(101, [event()])])
        self.observer = Observer(self.client, map_data=make_map())
        self.observation = self.observer.poll()
        self.agent = self.observer.identity.agent_id(TANK)
        self.registry = TacticRegistry()
        self.registry.register(Tactic(TacticInfo(
            name="_guard_probe_current", summary="test only",
            requires=("has_units", "has_map")), guard_current))
        self.registry.register(Tactic(TacticInfo(
            name="_guard_probe_position", summary="test only",
            params=(Param("cell", REQUIRED, "cell", is_cell),),
            requires=("has_units", "has_map")), guard_position))
        executor = Executor(self.client, self.observer.identity,
                            validator=Validator(make_map()),
                            read_state=lambda: self.observer.poll().state,
                            sleep=lambda _: self.client.advance())
        self.layer = MicroLayer(self.observer, registry=self.registry, executor=executor)
        self.commander = Commander(self.layer, self.observer)

    def test_commander_to_runtime_completes_only_input_operation(self):
        request = CallRequest(tactic="_guard_probe_position", units=(self.agent,),
                              params={"cell": (2, 2)})
        accepted = self.commander.call([request], self.observation)[0]
        self.assertTrue(accepted.accepted, accepted.error)
        outcomes = self.layer.tick(self.observation)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].evidence, "native_input_observed")
        self.assertEqual(len(self.client.sent), 1)
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(self.observer.last_state.object(TANK).coordinates.cell, (1, 1))

    def test_current_tactic_runs_with_pool_subject(self):
        intents = self.registry.run("_guard_probe_current", observation=self.observation,
                                    subject=UnitPool(self.observation, self.observer.identity),
                                    frame=100)
        self.assertEqual(intents[0].units, (self.agent,))
        self.assertEqual(intents[0].kind, "guard_current")

    def test_missing_bad_parameter_or_empty_units_rejected(self):
        for params, units in (({}, (self.agent,)), ({"cell": None}, (self.agent,)),
                              ({"cell": (2, 2)}, ())):
            request = CallRequest(tactic="_guard_probe_position", units=units, params=params)
            self.assertFalse(self.commander.call([request], self.observation)[0].accepted)
        self.assertEqual(self.client.sent, [])

    def test_missing_map_rejected_before_execution(self):
        observation = replace(self.observation, map_data=None)
        request = CallRequest(tactic="_guard_probe_current", units=(self.agent,))
        self.assertFalse(self.commander.call([request], observation)[0].accepted)
        self.assertEqual(self.client.sent, [])


if __name__ == "__main__":
    unittest.main()
