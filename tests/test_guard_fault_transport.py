"""Fixed test faults and server rejection handling; not production capabilities."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from ra2agent.constants import UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.client import CommandResult
from ra2agent.engine.proto import fmap, repeated_ints
from ra2agent.engine.state import Coordinates, GameObject
from ra2agent.engine.validate import Validator
from ra2agent.errors import CommandFailed
from tests.guard_fault_transport import FAULT_ERRORS, GuardFaultTransport, fault_request
from tests.test_guard_interface import GuardCase, NATIVE_ID, TANK, state
from tests.test_executor import make_map


class TestGuardFaultTransport(GuardCase):
    def native_fixture(self):
        return json.loads((Path(__file__).parent / "data/guard_rejections_native.json").read_text())

    def test_real_server_refusals_echo_the_faulty_requests(self):
        fixture = self.native_fixture()
        self.assertEqual({c["label"] for c in fixture["cases"]}, set(FAULT_ERRORS))
        for case in fixture["cases"]:
            with self.subTest(fault=case["label"]):
                request = bytes.fromhex(case["request_hex"])
                self.assertEqual(request, fault_request(bytes.fromhex(case["valid_request_hex"]),
                                                       case["label"], **fixture["fault_identities"]))
                result = case["result"]
                self.assertEqual(result["code"], 1)
                self.assertEqual(result["error"], FAULT_ERRORS[case["label"]])
                query, echo = fmap(request), fmap(bytes.fromhex(result["payload"]))
                # Protobuf reserializes repeated actors as packed and omits default zero fields.
                self.assertEqual(list(repeated_ints(query[1])), list(repeated_ints(echo[1])))
                for number in (2, 3, 5, 6, 7):
                    self.assertEqual(query.get(number, [(0, 0)])[0][1],
                                     echo.get(number, [(0, 0)])[0][1])
                self.assertEqual(bool(query.get(4)), bool(echo.get(4)))
                if 4 in query:
                    q, e = fmap(query[4][0][1]), fmap(echo[4][0][1])
                    for number in (1, 2, 3):
                        self.assertEqual(q.get(number, [(0, 0)])[0][1],
                                         e.get(number, [(0, 0)])[0][1])
                self.assertEqual(case["transmissions"], 1)
                self.assertTrue(case["tracked_unchanged_after_refusal"])

    def test_real_refusal_replies_fail_executor_once_without_reading_echo(self):
        fixture = self.native_fixture()
        for case in fixture["cases"]:
            with self.subTest(fault=case["label"]):
                actor_data = dict(fixture["actor"])
                for key in ("coordinates", "destination"):
                    actor_data[key] = Coordinates(**actor_data[key])
                actor = GameObject(**actor_data)
                frame = fmap(bytes.fromhex(case["valid_request_hex"]))[7][0][1]
                base = state(frame)
                house = replace(base.player_house(), pointer=actor.house,
                                array_index=fixture["house_index"])
                initial = replace(base, objects=(actor,), houses=(house,))
                executor = self.build(initial)
                self.agent = self.identity.agent_id(actor.pointer)
                executor.validator = Validator(make_map(144))
                result_data = dict(case["result"])
                result_data["payload"] = bytes.fromhex(result_data["payload"])
                self.client.send_command = Mock(return_value=CommandResult(**result_data))
                adapter = GuardFaultTransport(self.client)
                adapter.arm(case["label"], **fixture["fault_identities"])
                executor.client = adapter
                with self.assertRaises(CommandFailed) as caught:
                    executor.execute(self.intent(), initial)
                self.assertIn(case["result"]["error"], str(caught.exception))
                self.assertEqual(adapter.requests[0]["request_hex"], case["request_hex"])
                self.assertEqual(len(adapter.requests), 1)
                self.assertEqual(self.client.state_calls, 1)

    def test_fixed_faults_preserve_guard_protocol_and_original_bytes(self):
        body = payloads.guard_order(TANK, UnitAction.GUARD_CURRENT, NATIVE_ID, 123, 300)
        expected_fields = {
            "wrong_native_id": 5, "wrong_house": 6, "stale_basis": 7,
            "future_basis": 7, "current_with_coordinates": 4,
            "position_without_coordinates": 2, "object_target": 3,
            "negative_coordinates": 4, "outside_map": 4,
            "unknown_actor": 1, "foreign_actor": 1, "infantry_actor": 1,
        }
        for fault, number in expected_fields.items():
            with self.subTest(fault=fault):
                altered = fault_request(body, fault, other_house=456,
                                        foreign_pointer=789, foreign_native_id=888,
                                        infantry_pointer=987, infantry_native_id=654)
                fields = fmap(altered)
                self.assertNotEqual(altered, body)
                self.assertEqual(len(fields[1]), 1)
                self.assertIn(fields[2][0][1], (13, 14))
                self.assertNotEqual(fields.get(number), fmap(body).get(number))
                self.assertEqual(fields[6], fmap(body)[6] if fault != "wrong_house" else [(0, 456)])
                if fault == "foreign_actor":
                    self.assertEqual(fields[5], [(0, 888)])
        self.assertEqual(set(expected_fields), set(FAULT_ERRORS))

    def test_unknown_fault_invalid_baseline_and_missing_identity_refuse(self):
        body = payloads.guard_order(TANK, UnitAction.GUARD_CURRENT, NATIVE_ID, 123, 300)
        for fault, blob in (("arbitrary_mission", body),
                            ("wrong_native_id", payloads.unit_order((TANK,), UnitAction.MOVE)),
                            ("foreign_actor", body), ("infantry_actor", body),
                            ("wrong_house", body)):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                fault_request(blob, fault)
        with self.assertRaises(ValueError):
            fault_request(body, "wrong_house", other_house=123)
        with self.assertRaises(ValueError):
            fault_request(body, "foreign_actor", foreign_pointer=789)
        with self.assertRaises(ValueError):
            fault_request(payloads.guard_order(TANK, UnitAction.GUARD_CURRENT,
                                              NATIVE_ID, 123, 150), "stale_basis")

    def test_adapter_is_single_use_and_preserves_rejection_echo(self):
        client = Mock()
        reply = CommandResult(type="UnitOrder", payload=b"request echo", code=1,
                              error=FAULT_ERRORS["wrong_native_id"], command_id=7)
        client.send_command.return_value = reply
        adapter = GuardFaultTransport(client)
        adapter.arm("wrong_native_id")
        with self.assertRaises(ValueError):
            adapter.arm("wrong_house")
        result = adapter.guard_order(TANK, UnitAction.GUARD_CURRENT, NATIVE_ID, 123, 300)
        self.assertIs(result, reply)
        self.assertFalse(result.ok)
        self.assertIsNone(adapter.armed)
        client.send_command.assert_called_once()
        adapter.guard_order(TANK, UnitAction.GUARD_CURRENT, NATIVE_ID, 123, 301)
        client.guard_order.assert_called_once()
        self.assertEqual(len(adapter.requests), 2)

    def test_executor_rejects_nonzero_reply_without_parsing_echo_or_retry(self):
        initial = state(300)
        executor = self.build(initial)
        self.client.send_command = Mock(return_value=CommandResult(
            type="UnitOrder", payload=b"invalid as a GameState", code=1,
            error=FAULT_ERRORS["wrong_native_id"], command_id=7))
        adapter = GuardFaultTransport(self.client)
        adapter.arm("wrong_native_id")
        executor.client = adapter
        with self.assertRaises(CommandFailed) as caught:
            executor.execute(self.intent(), initial)
        self.assertIn(FAULT_ERRORS["wrong_native_id"], str(caught.exception))
        self.assertEqual(len(adapter.requests), 1)
        self.assertEqual(self.client.state_calls, 1)
        self.assertEqual(self.client.sent, [])


if __name__ == "__main__":
    unittest.main()
