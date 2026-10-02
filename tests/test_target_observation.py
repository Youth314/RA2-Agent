"""U08 只读目标的编码与合法投影；合成数据不证明游戏实际开火。"""
import unittest

from ra2agent.constants import AbstractType
from ra2agent.engine.observation import Observer, ObservedTarget
from ra2agent.engine.proto import pb_bytes, pb_uint, tag
from ra2agent.engine.state import ActualTarget, GameState, parse_object
from ra2agent.errors import ProtocolError
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_game_state,
                            build_house, build_object)
from tests.test_observation import FakeClient, make_map

ACTOR = 0xA1
TARGET = 0xB1
ACTOR_NATIVE = 1043800
TARGET_NATIVE = 1043823


def target_blob(status=3, *, native=TARGET_NATIVE, pointer=TARGET,
                kind=AbstractType.UNIT, rtti=52):
    blob = pb_uint(1, status)
    if status == 3:
        blob += pb_bytes(2, pb_uint(1, native) + pb_uint(2, rtti))
        blob += pb_uint(3, kind) + pb_uint(4, pointer)
    return blob


def obj(pointer, house=PLAYER_HOUSE, native=None, actual=None, **options):
    blob = build_object(pointer, house=house, x=384, y=384, **options)
    if native is not None:
        blob += pb_uint(21, native)
    if actual is not None:
        blob += pb_bytes(22, actual)
    return blob


def state(frame=100, actor=None, target=None, version=1):
    objects = [actor if actor is not None else
               obj(ACTOR, native=ACTOR_NATIVE, actual=target_blob())]
    if target is not False:
        objects.append(target if target is not None else
                       obj(TARGET, native=TARGET_NATIVE))
    return GameState.parse(build_game_state(
        frame=frame, houses=[build_house(PLAYER_HOUSE, current_player=True),
                             build_house(ENEMY_HOUSE)], objects=objects)
                           + pb_uint(19, version))


class TestTargetWire(unittest.TestCase):
    def test_legacy_object_and_game_state_remain_absent(self):
        old = GameState.parse(build_game_state(objects=[obj(ACTOR)]))
        self.assertEqual(old.target_observation_version, 0)
        self.assertIsNone(old.object(ACTOR).actual_target)

    def test_four_states_are_distinct(self):
        self.assertIsNone(parse_object(obj(ACTOR)).actual_target)
        for code in (1, 2, 3):
            with self.subTest(code=code):
                actual = parse_object(obj(ACTOR, actual=target_blob(code))).actual_target
                self.assertEqual(actual.status, code)
                self.assertEqual(actual.native_id, TARGET_NATIVE if code == 3 else None)

    def test_concrete_type_differs_from_abstract_reference(self):
        for kind in (1, 2, 6, 15):
            with self.subTest(kind=kind):
                actual = ActualTarget.parse(target_blob(kind=kind))
                self.assertEqual(actual.reference.m_rtti, 52)
                self.assertEqual(actual.object_type, kind)

    def test_native_id_uint32_bit_pattern(self):
        for wire_value, expected in ((0, 0), (-1, 0xFFFFFFFF),
                                     (-0x80000000, 0x80000000),
                                     (0xFFFFFFFF, 0xFFFFFFFF)):
            with self.subTest(value=wire_value):
                self.assertEqual(ActualTarget.parse(target_blob(native=wire_value)).native_id,
                                 expected)
        zero = (pb_uint(1, 3) + pb_bytes(2, pb_uint(2, 52))
                + pb_uint(3, 1) + pb_uint(4, TARGET))
        self.assertEqual(ActualTarget.parse(zero).native_id, 0)

    def test_none_and_unobservable_forbid_identity_payload(self):
        for code in (1, 2):
            for extra in (pb_bytes(2, b""), pb_uint(3, 1), pb_uint(4, TARGET)):
                with self.subTest(code=code, extra=extra):
                    with self.assertRaises(ProtocolError):
                        ActualTarget.parse(pb_uint(1, code) + extra)

    def test_invalid_shape_or_reference_fails_closed(self):
        bad = [b"", pb_uint(1, 0), pb_uint(1, 9), pb_uint(1, 3),
               target_blob(rtti=11), target_blob(rtti=1), target_blob(pointer=0),
               target_blob(pointer=1 << 32), target_blob(kind=11),
               target_blob(native=1 << 40), target_blob(native=-0x80000001),
               pb_bytes(1, b"x"), target_blob() + pb_uint(1, 2),
               pb_uint(1, 3) + pb_uint(2, 9) + pb_uint(3, 1) + pb_uint(4, TARGET)]
        for blob in bad:
            with self.subTest(blob=blob):
                with self.assertRaises(ProtocolError):
                    ActualTarget.parse(blob)

    def test_missing_object_payload_fields_are_rejected(self):
        parts = [pb_uint(1, 3), pb_bytes(2, pb_uint(1, TARGET_NATIVE) + pb_uint(2, 52)),
                 pb_uint(3, 1), pb_uint(4, TARGET)]
        for missing in range(1, 4):
            with self.subTest(missing=missing):
                with self.assertRaises(ProtocolError):
                    ActualTarget.parse(b"".join(p for i, p in enumerate(parts) if i != missing))

    def test_truncated_nested_messages_do_not_become_none(self):
        bad = [pb_uint(1, 2) + b"\x08\x80",
               pb_uint(1, 2) + b"\x2a\x0aabc",  # Unknown length-delimited field truncated.
               tag(1, 5) + b"x", tag(1, 1) + b"x",
               b"\x08" + b"\xff" * 10, b"\x00\x02"]
        for blob in bad:
            with self.subTest(blob=blob):
                with self.assertRaises(ProtocolError):
                    ActualTarget.parse(blob)
        with self.assertRaises(ProtocolError):
            parse_object(obj(ACTOR) + tag(22, 2) + b"\x09" + pb_uint(1, 2))

    def test_object_field_wrong_wire_and_duplicates_rejected(self):
        for extra in (pb_uint(22, 2),
                      pb_bytes(22, target_blob(2)) + pb_bytes(22, target_blob(2))):
            with self.assertRaises(ProtocolError):
                parse_object(obj(ACTOR) + extra)

    def test_version_wire_is_uint32(self):
        for extra in (pb_bytes(19, b"x"), pb_uint(19, 1 << 32)):
            with self.assertRaises(ProtocolError):
                GameState.parse(build_game_state() + extra)

    def test_unknown_added_field_is_compatible(self):
        parsed = ActualTarget.parse(target_blob() + pb_bytes(99, b"future"))
        self.assertEqual(parsed.object_pointer, TARGET)


class TestTargetProjection(unittest.TestCase):
    def setUp(self):
        self.observer = Observer(FakeClient(), map_data=make_map([[0] * 4] * 4))

    def observe(self, snapshot):
        self.observer.absorb(snapshot)
        observation = self.observer.observe()
        actor_id = self.observer.identity.agent_id(ACTOR)
        return observation, observation.actual_targets.get(actor_id)

    def test_maps_to_stable_id_and_clears_raw_references(self):
        snapshot = state()
        observation, target = self.observe(snapshot)
        self.assertEqual(target, ObservedTarget("object", self.observer.identity.agent_id(TARGET)))
        self.assertNotEqual(target.agent_id, TARGET_NATIVE)
        self.assertFalse(hasattr(target, "object_pointer"))
        self.assertIsNone(observation.own[0].actual_target)
        self.assertIsNotNone(snapshot.object(ACTOR).actual_target)

    def test_unprovided_version_and_absent_object_field(self):
        for snapshot in (state(version=0), state(version=2),
                         state(actor=obj(ACTOR, native=ACTOR_NATIVE))):
            with self.subTest(version=snapshot.target_observation_version):
                self.assertEqual(self.observe(snapshot)[1], ObservedTarget("not_provided"))

    def test_none_and_unobservable_are_not_object_matches(self):
        for code, expected in ((1, "unobservable"), (2, "none")):
            snapshot = state(actor=obj(ACTOR, native=ACTOR_NATIVE, actual=target_blob(code)))
            self.assertEqual(self.observe(snapshot)[1], ObservedTarget(expected))

    def test_native_identity_mismatch_is_unobservable(self):
        self.assertEqual(self.observe(state(target=obj(TARGET, native=9)))[1],
                         ObservedTarget("unobservable"))

    def test_target_absent_limbo_dead_or_changed_type_is_unobservable(self):
        for target in (False, obj(TARGET, native=TARGET_NATIVE, in_limbo=True),
                       obj(TARGET, native=TARGET_NATIVE, health=0),
                       obj(TARGET, native=TARGET_NATIVE, on_map=False),
                       obj(TARGET, native=TARGET_NATIVE, object_type=AbstractType.BUILDING),
                       obj(TARGET)):  # own native identity not provided
            with self.subTest(target=target):
                self.assertEqual(self.observe(state(target=target))[1],
                                 ObservedTarget("unobservable"))

    def test_foreign_reference_requires_both_dll_gate_and_legal_set(self):
        foreign = obj(TARGET, house=ENEMY_HOUSE)
        self.assertEqual(self.observe(state(target=foreign))[1].status, "object")
        self.observer.map_data = make_map([[1] * 4] * 4)
        self.assertEqual(self.observe(state(frame=101, target=foreign))[1],
                         ObservedTarget("unobservable"))
        self.observer.map_data = None
        self.assertEqual(self.observe(state(frame=102, target=foreign))[1],
                         ObservedTarget("unobservable"))

    def test_hidden_foreign_does_not_use_stale_identity_or_raw_state(self):
        foreign = obj(TARGET, house=ENEMY_HOUSE)
        observation, _ = self.observe(state(target=foreign))
        self.observer.map_data = make_map([[1] * 4] * 4)
        hidden = state(frame=101, target=foreign)
        observation, target = self.observe(hidden)
        self.assertIsNotNone(observation.state.object(TARGET))
        self.assertIsNotNone(self.observer.identity.agent_id(TARGET))
        self.assertEqual(target, ObservedTarget("unobservable"))
        self.assertEqual(observation.visible_enemies, ())

    def test_foreign_actor_targets_never_exposed(self):
        foreign = obj(TARGET, house=ENEMY_HOUSE, actual=target_blob(pointer=ACTOR))
        observation, _ = self.observe(state(target=foreign))
        self.assertIsNone(observation.visible_enemies[0].actual_target)
        self.assertEqual(set(observation.actual_targets),
                         {self.observer.identity.agent_id(ACTOR)})

    def test_pointer_reuse_does_not_match_previous_native_target(self):
        _, old = self.observe(state())
        _, current = self.observe(state(frame=101, target=obj(TARGET, native=TARGET_NATIVE + 1)))
        self.assertEqual(current, ObservedTarget("unobservable"))
        new_actor = obj(ACTOR, native=ACTOR_NATIVE, actual=target_blob(native=TARGET_NATIVE + 1))
        _, corrected = self.observe(state(frame=102, actor=new_actor,
                                          target=obj(TARGET, native=TARGET_NATIVE + 1)))
        self.assertEqual(corrected.status, "object")
        self.assertNotEqual(corrected.agent_id, old.agent_id)

    def test_absent_target_grace_period_does_not_revive_reference(self):
        self.observe(state())
        self.assertEqual(self.observe(state(frame=101, target=False))[1],
                         ObservedTarget("unobservable"))
        self.assertIsNotNone(self.observer.identity.agent_id(TARGET))

    def test_no_absorb_means_no_fresh_target_identity(self):
        self.observe(state())
        observation = self.observer.observe(state(frame=101))
        self.assertEqual(observation.actual_targets[self.observer.identity.agent_id(ACTOR)],
                         ObservedTarget("unobservable"))

    def test_actor_invalid_state_cannot_report_none(self):
        for changes in ({"health": 0}, {"on_map": False}):
            snapshot = state(actor=obj(ACTOR, native=ACTOR_NATIVE,
                                       actual=target_blob(2), **changes))
            self.assertEqual(self.observe(snapshot)[1], ObservedTarget("unobservable"))

    def test_actor_missing_native_identity_cannot_report_none(self):
        snapshot = state(actor=obj(ACTOR, actual=target_blob(2)))
        self.assertEqual(self.observe(snapshot)[1], ObservedTarget("unobservable"))

    def test_dll_unobservable_never_resolves_hidden_target(self):
        # v1 DLL emits only status=1 for fog/cloak/disguise/unsupported targets.
        snapshot = state(actor=obj(ACTOR, native=ACTOR_NATIVE, actual=target_blob(1)),
                         target=obj(TARGET, house=ENEMY_HOUSE))
        self.assertEqual(self.observe(snapshot)[1], ObservedTarget("unobservable"))


if __name__ == "__main__":
    unittest.main()
