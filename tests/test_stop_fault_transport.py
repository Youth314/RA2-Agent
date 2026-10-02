"""Isolated fixed faults; synthetic replies are not evidence of DLL rejection."""
import unittest
import json
from pathlib import Path
from dataclasses import replace
from unittest.mock import Mock
from ra2agent.constants import UnitAction
from ra2agent.engine import payloads
from ra2agent.engine.client import CommandResult
from ra2agent.engine.identity import IdentityTable
from ra2agent.engine.proto import fmap, pb_uint, repeated_ints
from ra2agent.engine.state import Coordinates, GameObject
from ra2agent.engine.validate import Validator
from ra2agent.errors import CommandFailed, Timeout
from ra2agent.runtime.executor import Executor
from ra2agent.runtime.intents import Stop
from tests.stop_fault_transport import FAULT_ERRORS, StopFaultTransport, fault_request
from tests.test_stop_interface import StopClient, state
from tests.test_executor import TANK, make_map

FIXTURES = dict(other_house=456, foreign_pointer=789, foreign_native_id=888,
                infantry_pointer=987, infantry_native_id=654)


class TestStopFaultTransport(unittest.TestCase):
    def test_real_replies_echo_fixed_faults_and_recorded_windows(self):
        fixture = json.loads((Path(__file__).parent/'data/stop_rejections_native.json').read_text())
        self.assertEqual({c['label'] for c in fixture['cases']}, set(FAULT_ERRORS))
        for case in fixture['cases']:
            with self.subTest(fault=case['label']):
                body=bytes.fromhex(case['request_hex'])
                original=bytes.fromhex(case['valid_request_hex'])
                self.assertEqual(body, fault_request(original,case['label'],**fixture['fault_identities']))
                reply=case['result']
                self.assertEqual(reply['code'],1)
                self.assertEqual(reply['error'],FAULT_ERRORS[case['label']])
                query,echo=fmap(body),fmap(bytes.fromhex(reply['payload']))
                self.assertEqual(list(repeated_ints(query.get(1,()))),list(repeated_ints(echo.get(1,()))))
                for n in (2,3,5,6,7):
                    self.assertEqual(query.get(n,[(0,0)])[0][1],echo.get(n,[(0,0)])[0][1])
                self.assertEqual(query.get(4),echo.get(4))
                self.assertEqual(case['transmissions'],1)
                window=fixture['recording_windows'][case['label']]
                self.assertTrue(window['complete_window'])
                self.assertTrue(window['unchanged'])
                self.assertEqual(window['new_idle_count'],0)
                self.assertGreaterEqual(window['last_frame']-window['first_frame'],45)

    def test_real_refusal_through_executor_no_retry_or_echo_parse(self):
        fixture = json.loads((Path(__file__).parent/'data/stop_rejections_native.json').read_text())
        for case in fixture['cases']:
            with self.subTest(fault=case['label']):
                actor_data=dict(fixture['actor'])
                for key in ('coordinates','destination'):
                    actor_data[key]=Coordinates(**actor_data[key])
                actor=GameObject(**actor_data)
                frame=fmap(bytes.fromhex(case['valid_request_hex']))[7][0][1]
                base=state(frame)
                house=replace(base.player_house(),pointer=actor.house,array_index=fixture['house_index'])
                initial=replace(base,objects=(actor,),houses=(house,))
                client=StopClient([initial]);ids=IdentityTable();ids.update(initial)
                reply=dict(case['result']);reply['payload']=bytes.fromhex(reply['payload'])
                client.send_command=Mock(return_value=CommandResult(**reply))
                adapter=StopFaultTransport(client);adapter.arm(case['label'],**fixture['fault_identities'])
                executor=Executor(adapter,ids,validator=Validator(make_map(144)))
                with self.assertRaises(CommandFailed) as caught:
                    executor.execute(Stop(units=(ids.agent_id(actor.pointer),)),initial)
                self.assertIn(case['result']['error'],str(caught.exception))
                self.assertEqual(adapter.requests[0]['request_hex'],case['request_hex'])
                self.assertEqual(len(adapter.requests),1)
                self.assertEqual(client.state_calls,1)
                self.assertEqual(client.sent,[])

    def test_fixed_payloads(self):
        body = payloads.stop_order(TANK, 111, 123, 300)
        baseline = fmap(body)
        expected_changes = {
            'wrong_native_id': {5}, 'wrong_house': {6}, 'stale_basis': {7},
            'future_basis': {7}, 'empty_actors': {1}, 'multiple_actors': {1},
            'missing_native_id': {5}, 'missing_house': {6}, 'coordinates': {4},
            'object_target': {3}, 'foreign_actor': {1, 5}, 'infantry_actor': {1, 5},
        }
        self.assertEqual(set(expected_changes), set(FAULT_ERRORS))
        for fault, changed in expected_changes.items():
            with self.subTest(fault=fault):
                actual = fmap(fault_request(body, fault, **FIXTURES))
                self.assertEqual(actual[2], [(0, UnitAction.PLAYER_STOP)])
                self.assertEqual({n for n in set(actual)|set(baseline)
                                  if actual.get(n) != baseline.get(n)}, changed)
                if fault == 'empty_actors': self.assertNotIn(1, actual)
                if fault == 'multiple_actors': self.assertEqual(actual[1], [(0,TANK),(0,TANK)])
                if fault == 'coordinates': self.assertEqual(actual[4], [(2,b'')])

    def test_refuse_invalid_baseline_and_fixture(self):
        body = payloads.stop_order(TANK, 111, 123, 300)
        for bad in (payloads.unit_order((TANK,), UnitAction.STOP), body+pb_uint(1,TANK),
                    payloads.stop_order(TANK,111,123,300)+pb_uint(3,TANK)):
            with self.assertRaises(ValueError): fault_request(bad,'wrong_native_id')
        for fault in ('arbitrary', 'wrong_house', 'foreign_actor', 'infantry_actor'):
            with self.assertRaises(ValueError): fault_request(body,fault)
        for kwargs in (dict(other_house=123), dict(other_house=True)):
            with self.assertRaises(ValueError): fault_request(body,'wrong_house',**kwargs)
        with self.assertRaises(ValueError):
            fault_request(payloads.stop_order(TANK,111,123,150),'stale_basis')
        with self.assertRaises(ValueError):
            fault_request(payloads.stop_order(TANK,111,123,0xFFFFFFFF),'future_basis')

    def test_every_rejection_finishes_without_parsing_echo_or_retry(self):
        for fault, error in FAULT_ERRORS.items():
            with self.subTest(fault=fault):
                initial=state(300);client=StopClient([initial]);ids=IdentityTable();ids.update(initial)
                client.send_command=Mock(return_value=CommandResult(type='UnitOrder',
                    payload=b'not a state',code=1,error=error))
                adapter=StopFaultTransport(client);adapter.arm(fault,**FIXTURES)
                executor=Executor(adapter,ids,validator=Validator(make_map()))
                with self.assertRaises(CommandFailed):
                    executor.execute(Stop(units=(ids.agent_id(TANK),)),initial)
                self.assertEqual(client.state_calls,1)
                self.assertEqual(len(adapter.requests),1)
                self.assertIsNone(adapter.armed)
                self.assertEqual(client.sent,[])

    def test_single_use_and_unknown_transport_does_not_retry(self):
        client=Mock();adapter=StopFaultTransport(client);adapter.arm('wrong_native_id')
        with self.assertRaises(ValueError): adapter.arm('wrong_house')
        client.send_command.side_effect=Timeout('unknown transport')
        with self.assertRaises(Timeout): adapter.stop_order(TANK,111,123,300)
        self.assertIsNone(adapter.armed);self.assertEqual(len(adapter.requests),1)
        client.send_command.assert_called_once()
        adapter.stop_order(TANK,111,123,301)
        client.stop_order.assert_called_once_with(TANK,111,123,301)


if __name__ == '__main__': unittest.main()
