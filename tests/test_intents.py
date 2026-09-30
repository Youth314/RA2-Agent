"""意图 schema 与决策日志的测试。"""
import json
import os
import tempfile
import unittest

from ra2agent.errors import Ra2Error
from ra2agent.runtime.intents import (TERMINAL_STATES, DecisionLog, Deploy, Hold,
                              Intent, IntentState, Layer, MoveTo, Place,
                              Produce, Scope, Sell, Stance, frames_for,
                              registered_kinds)


class TestScope(unittest.TestCase):
    def test_requires_something(self):
        with self.assertRaises(ValueError):
            Scope()

    def test_empty_is_explicit(self):
        # 阵营级意图（生产）不涉及对象，故允许显式声明为空，而不是给个假对象
        scope = Scope.empty()
        self.assertTrue(scope.is_empty)
        self.assertEqual(scope.to_dict(), {"objects": [], "region": None})
        self.assertEqual(Scope.from_dict(scope.to_dict()), scope)

    def test_non_empty_is_not_empty(self):
        self.assertFalse(Scope(objects=(1,)).is_empty)

    def test_objects_only(self):
        scope = Scope(objects=[1, 2])
        self.assertEqual(scope.objects, (1, 2))
        self.assertIsNone(scope.region)

    def test_region_only(self):
        scope = Scope(region=(0, 0, 5, 5))
        self.assertEqual(scope.region, (0, 0, 5, 5))
        self.assertEqual(scope.objects, ())

    def test_round_trip(self):
        scope = Scope(objects=[3], region=(1, 2, 3, 4))
        restored = Scope.from_dict(scope.to_dict())
        self.assertEqual(restored, scope)

    def test_equality(self):
        self.assertEqual(Scope(objects=[1]), Scope(objects=[1]))
        self.assertNotEqual(Scope(objects=[1]), Scope(objects=[2]))


class TestIntentEnvelope(unittest.TestCase):
    def test_ids_are_unique(self):
        self.assertNotEqual(MoveTo().id, MoveTo().id)

    def test_registered_kinds_are_sorted(self):
        kinds = registered_kinds()
        self.assertEqual(kinds, sorted(kinds))
        for expected in ("move_to", "attack", "hold", "deploy", "produce",
                         "place", "sell"):
            self.assertIn(expected, kinds)

    def test_kind_is_filled_by_registry(self):
        self.assertEqual(MoveTo().kind, "move_to")
        self.assertEqual(Sell().kind, "sell")

    def test_default_state_is_active(self):
        self.assertEqual(MoveTo().state, IntentState.ACTIVE)
        self.assertFalse(MoveTo().is_terminal())

    def test_terminal_states(self):
        for state in TERMINAL_STATES:
            with self.subTest(state=state):
                intent = MoveTo()
                intent.state = state
                self.assertTrue(intent.is_terminal())

    def test_ttl_expiry(self):
        intent = MoveTo(created_frame=100, ttl_frames=50)
        self.assertEqual(intent.expires_at(), 150)
        self.assertFalse(intent.is_expired(149))
        self.assertTrue(intent.is_expired(150))
        self.assertTrue(intent.is_expired(200))

    def test_no_ttl_never_expires(self):
        intent = MoveTo(created_frame=100, ttl_frames=None)
        self.assertIsNone(intent.expires_at())
        self.assertFalse(intent.is_expired(10 ** 9))

    def test_child_links_parent(self):
        parent = Produce(type_pointer=0x1)
        child = parent.child(MoveTo(units=(1,), cell=(2, 3)))
        self.assertEqual(child.parent, parent.id)


class TestSerialisation(unittest.TestCase):
    def test_round_trip_preserves_fields(self):
        original = MoveTo(layer=Layer.L1_TACTIC, issuer="human",
                          scope=Scope(objects=(7, 8)),
                          created_frame=42, ttl_frames=120,
                          units=(7, 8), cell=(10, 11),
                          stance=Stance.PASSIVE)
        restored = MoveTo.from_dict(original.to_dict())
        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.layer, Layer.L1_TACTIC)
        self.assertEqual(restored.issuer, "human")
        self.assertEqual(restored.scope, original.scope)
        self.assertEqual(restored.created_frame, 42)
        self.assertEqual(restored.ttl_frames, 120)
        self.assertEqual(restored.cell, original.cell)
        self.assertEqual(restored.stance, Stance.PASSIVE)

    def test_from_dict_dispatches_on_kind(self):
        restored = Intent.from_dict(Deploy(units=(5,)).to_dict())
        self.assertIsInstance(restored, Deploy)
        self.assertEqual(restored.units, (5,))

    def test_json_encodable(self):
        for intent in (MoveTo(units=(1,), cell=(2, 3)), Produce(type_pointer=9),
                       Place(building=4, cell=(1, 1)), Sell(buildings=(6,))):
            with self.subTest(kind=intent.kind):
                text = json.dumps(intent.to_dict())
                restored = Intent.from_dict(json.loads(text))
                self.assertEqual(restored.kind, intent.kind)

    def test_unknown_kind_raises(self):
        with self.assertRaises(Ra2Error):
            Intent.from_dict({"kind": "nonexistent"})

    def test_extra_keys_are_ignored(self):
        data = Hold(units=(1,)).to_dict()
        data["bogus"] = 123
        restored = Intent.from_dict(data)
        self.assertIsInstance(restored, Hold)


class TestFramesFor(unittest.TestCase):
    def test_conversion(self):
        self.assertEqual(frames_for(0, fps=44), 1)      # 至少一帧
        self.assertEqual(frames_for(1, fps=44), 44)
        self.assertEqual(frames_for(180, fps=44), 7920)  # 三分钟

    def test_rounds(self):
        self.assertEqual(frames_for(0.5, fps=44), 22)


class TestDecisionLog(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "match.jsonl")

    def tearDown(self):
        for name in os.listdir(self.dir):
            os.unlink(os.path.join(self.dir, name))
        os.rmdir(self.dir)

    def read(self):
        with open(self.path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_writes_one_line_per_record(self):
        with DecisionLog(self.path) as log:
            log.record(100, "intent_issued", intent=MoveTo(units=(1,)))
            log.record(104, "command_sent", intent=MoveTo(units=(1,)),
                       detail={"command": "UnitOrder"})
        entries = self.read()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["frame"], 100)
        self.assertEqual(entries[0]["event"], "intent_issued")
        self.assertEqual(entries[1]["detail"], {"command": "UnitOrder"})

    def test_records_intent_id_and_layer(self):
        intent = MoveTo(layer=Layer.L2_COMMAND)
        with DecisionLog(self.path) as log:
            log.record(7, "intent_issued", intent=intent)
        entry = self.read()[0]
        self.assertEqual(entry["intent_id"], intent.id)
        self.assertEqual(entry["layer"], int(Layer.L2_COMMAND))

    def test_facts_are_stored(self):
        with DecisionLog(self.path) as log:
            log.record(9, "intent_issued", facts={"enemy_tanks": 3,
                                                  "cell": [10, 11]})
        self.assertEqual(self.read()[0]["facts"],
                         {"enemy_tanks": 3, "cell": [10, 11]})

    def test_appends_across_opens(self):
        with DecisionLog(self.path) as log:
            log.record(1, "a")
        with DecisionLog(self.path) as log:
            log.record(2, "b")
        self.assertEqual([e["frame"] for e in self.read()], [1, 2])

    def test_is_flushed_immediately(self):
        log = DecisionLog(self.path)
        log.record(1, "a")
        self.assertEqual(len(self.read()), 1)   # 未关闭也能读到
        log.close()


if __name__ == "__main__":
    unittest.main()
