"""原版事件的只读解析；真实 Event 样本 + 合成 GameState 信封。

这些测试不证明新的引擎下令路径生效，也不连接游戏。
"""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import unittest

from ra2agent.engine.native_events import NativeEvent, NativeMission, NativeTarget
from ra2agent.engine.proto import fmap, pb_bytes, pb_uint
from ra2agent.engine.state import GameState
from ra2agent.errors import ProtocolError
from tests.fixtures import build_game_state


SAMPLES = json.loads((Path(__file__).parent / "data/native_events.json")
                     .read_text())["samples"]


def sample(name):
    data = SAMPLES[name]
    return NativeEvent.parse(bytes.fromhex(data["raw_hex"]), data["source"])


def player(index=1):
    return pb_uint(1, index) + pb_uint(5, 1) + pb_uint(8, 123)


class TestNativeTarget(unittest.TestCase):
    def test_null_rtti_ignores_nonzero_id(self):
        target = sample("guard").mega_mission.follow
        self.assertNotEqual(target.m_id, 0)
        self.assertTrue(target.is_null)
        self.assertIsNone(target.cell)

    def test_cell_encoding(self):
        target = sample("guard").mega_mission.target
        self.assertEqual((target.m_id, target.m_rtti), (73033, 11))
        self.assertEqual(target.cell, (33, 73))
        self.assertFalse(target.is_null)

    def test_zero_cell_is_not_null(self):
        target = NativeTarget(0, 11)
        self.assertFalse(target.is_null)
        self.assertEqual(target.cell, (0, 0))

    def test_object_id_is_not_interpreted_as_cell(self):
        target = sample("escort").mega_mission.target
        self.assertEqual((target.m_id, target.m_rtti), (1043823, 52))
        self.assertIsNone(target.cell)

    def test_negative_cell_is_not_decoded(self):
        self.assertIsNone(NativeTarget(-1, 11).cell)

    def test_read_only(self):
        with self.assertRaises(FrozenInstanceError):
            NativeTarget(1, 11).m_id = 2


class TestNativeEvent(unittest.TestCase):
    def test_actual_guard(self):
        event = sample("guard")
        self.assertEqual((event.event_type, event.house_index, event.frame),
                         (4, 1, 11916))
        mission = event.mega_mission
        self.assertEqual(mission.mission, 11)
        self.assertEqual(mission.whom.m_id, 1043820)
        self.assertFalse(mission.is_planning_event)
        self.assertIsNone(mission.speed)

    def test_position_target(self):
        self.assertEqual(sample("guard_position").mega_mission.target.cell,
                         (42, 72))

    def test_object_targets_for_escort_and_structure(self):
        for name, target in (("escort", 1043823), ("guard_structure", 1043887)):
            with self.subTest(name=name):
                mission = sample(name).mega_mission
                self.assertEqual(mission.mission, 11)
                self.assertEqual(mission.target, NativeTarget(target, 52))
                self.assertTrue(mission.follow.is_null)

    def test_cmin_input_is_area_guard_not_harvest(self):
        self.assertEqual(sample("cmin_guard").mega_mission.mission, 11)

    def test_repair_guard_and_context_attack_are_different(self):
        self.assertEqual(sample("repair_guard").mega_mission.mission, 11)
        mission = sample("repair_target").mega_mission
        self.assertEqual(mission.mission, 1)
        self.assertEqual(mission.target, NativeTarget(1043823, 52))

    def test_actual_stale_frame_info_has_no_mission(self):
        event = sample("stale_frame_info")
        self.assertIn(8, fmap(event.raw))
        self.assertEqual(event.event_type, 28)
        self.assertIsNone(event.mega_mission)

    def test_idle_has_no_fabricated_actor(self):
        event = sample("stop")
        self.assertEqual(event.event_type, 6)
        self.assertIsNone(event.mega_mission)
        self.assertEqual(event.raw.hex(), SAMPLES["stop"]["raw_hex"])

    def test_cross_matched_oneof_is_not_used(self):
        for event_type, wrong_field in ((4, 9), (5, 8)):
            raw = pb_uint(4, event_type) + pb_bytes(wrong_field, pb_uint(2, 11))
            self.assertIsNone(NativeEvent.parse(raw, "do").mega_mission)

    def test_mega_mission_f_speed_is_not_a_follow_target(self):
        payload = pb_uint(2, -1) + pb_uint(5, -3) + pb_uint(6, 8)
        event = NativeEvent.parse(pb_uint(4, 5) + pb_bytes(9, payload), "do")
        mission = event.mega_mission
        self.assertEqual((mission.mission, mission.speed, mission.max_speed),
                         (-1, -3, 8))
        self.assertIsNone(mission.follow)
        self.assertIsNone(mission.is_planning_event)

    def test_missing_payload_is_distinct_from_empty_payload(self):
        missing = NativeEvent.parse(pb_uint(4, 4), "do")
        empty = NativeEvent.parse(pb_uint(4, 4) + pb_bytes(8, b""), "do")
        self.assertIsNone(missing.mega_mission)
        self.assertEqual(empty.mega_mission.mission, 0)
        self.assertIsNone(empty.mega_mission.whom)

    def test_unknown_event_preserves_raw_without_interpreting_payload(self):
        raw = pb_uint(4, 999) + pb_uint(8, 100)
        event = NativeEvent.parse(raw, "out")
        self.assertEqual(event.raw, raw)
        self.assertEqual(event.event_type, 999)
        self.assertIsNone(event.mega_mission)

    def test_wrong_wire_type_in_known_payload_is_rejected(self):
        with self.assertRaises(ProtocolError):
            NativeEvent.parse(pb_uint(4, 4) + pb_uint(8, 100), "do")

    def test_mission_decoder_rejects_other_event_types(self):
        with self.assertRaises(ProtocolError):
            NativeMission.parse(b"", 6)

    def test_read_only(self):
        event = sample("guard")
        with self.assertRaises(FrozenInstanceError):
            event.frame = 0
        with self.assertRaises(FrozenInstanceError):
            event.mega_mission.mission = 0


class TestGameStateNativeEvents(unittest.TestCase):
    def test_three_lists_preserve_sources_order_and_duplicates(self):
        raw = sample("guard").raw
        payload = build_game_state(houses=[player()])
        for field in (11, 12, 13):
            payload += pb_bytes(field, raw)
        state = GameState.parse(payload)
        self.assertEqual([e.source for e in state.native_events],
                         ["out", "do", "megamission"])
        self.assertEqual(len(state.native_events), 3)
        self.assertEqual(state.raw, payload)

    def test_public_view_excludes_foreign_player_orders(self):
        own = sample("guard").raw
        # Synthetic foreign-player header with a captured mission payload.
        foreign = pb_uint(4, 4) + pb_bytes(8, fmap(own)[8][0][1])
        payload = (build_game_state(houses=[player()])
                   + pb_bytes(12, foreign) + pb_bytes(12, own))
        events = GameState.parse(payload).native_events
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].house_index, 1)

    def test_legacy_state_without_events_remains_supported(self):
        state = GameState.parse(build_game_state(houses=[player()]))
        self.assertEqual(state.native_events, ())

    def test_public_view_requires_unique_player(self):
        for houses in ([], [player(), player(2)]):
            state = GameState.parse(build_game_state(houses=houses))
            with self.assertRaises(ProtocolError):
                _ = state.native_events

    def test_wrong_list_wire_type_is_rejected(self):
        with self.assertRaises(ProtocolError):
            GameState.parse(build_game_state() + pb_uint(12, 1))


if __name__ == "__main__":
    unittest.main()
