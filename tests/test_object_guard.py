"""U06/U07 offline identity, input-only evidence and real Commander lifecycle."""
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
from ra2agent.engine.native_events import NativeEvent
from ra2agent.engine.observation import Observer
from ra2agent.engine.proto import fmap, packed_varints, pb_bytes, pb_uint
from ra2agent.engine.state import GameState, cell_center, parse_object
from ra2agent.engine.validate import Validator
from ra2agent.errors import InvalidCommand, ProtocolError, Timeout
from ra2agent.runtime.executor import Executor
from ra2agent.runtime.intents import EscortUnit, GuardStructure, Intent, check_command_scope
from ra2agent.runtime.micro import MicroLayer
from ra2agent.tactics import Mode, TacticRegistry
from ra2agent.tactics.builtin.combat import TACTICS
from tests.fixtures import ENEMY_HOUSE, PLAYER_HOUSE, build_game_state
from tests.test_executor import FakeClient, TANK, ENEMY_TANK, make_map, make_state, tank

ROOT = Path(__file__).resolve().parents[1]
ACTOR_NATIVE, TARGET_NATIVE = 1043800, 0xFFFFFE80


def state(frame=100, *, events=(), target_type=1, version=1,
          actor_changes=None, target_changes=None):
    actor = parse_object(tank(TANK, (1, 1)) + pb_uint(21, ACTOR_NATIVE))
    target = parse_object(tank(ENEMY_TANK, (3, 3)) + pb_uint(21, TARGET_NATIVE))
    actor = replace(actor, **(actor_changes or {}))
    target = replace(target, **({'object_type': target_type} | (target_changes or {})))
    return replace(make_state(frame), objects=(actor, target),
                   object_guard_interface_version=version, _native_events=tuple(events))


def event(frame=101, *, actor=ACTOR_NATIVE, target=TARGET_NATIVE, mission=11,
          rtti=52, actor_rtti=52, house=0, timing=123, planning=False,
          destination=None, follow=None, event_type=4, source='out', executed=False):
    mega = (pb_bytes(1, pb_uint(1, actor) + pb_uint(2, actor_rtti))
            + pb_uint(2, mission)
            + pb_bytes(3, pb_uint(1, target - 2**32 if target >= 2**31 else target)
                       + pb_uint(2, rtti)) + pb_uint(6, int(planning)))
    for number, value in ((4, destination), (5, follow)):
        if value is not None:
            mega += pb_bytes(number, pb_uint(1, value[0]) + pb_uint(2, value[1]))
    return NativeEvent.parse(pb_uint(1, int(executed)) + pb_uint(2, house)
                             + pb_uint(3, frame) + pb_uint(4, event_type)
                             + pb_bytes(8, mega) + pb_uint(19, timing), source)


class GuardObjectClient(FakeClient):
    def guard_object_order(self, *args):
        self.sent.append(args)
        return self._reply('UnitOrder')


class TestObjectGuard(unittest.TestCase):
    def build(self, *states, kind=EscortUnit, **kwargs):
        self.client = GuardObjectClient(states)
        self.identity = IdentityTable()
        self.identity.update(states[0])
        self.actor = self.identity.agent_id(TANK)
        self.target = self.identity.agent_id(ENEMY_TANK)
        self.intent = kind(units=(self.actor,), target=self.target)
        self.executor = Executor(self.client, self.identity, validator=Validator(make_map()),
                                 sleep=lambda _: self.client.advance(), **kwargs)
        return self.executor.plan(self.intent, states[0])

    def test_schema_payload_transport_and_old_dll_absence(self):
        self.assertEqual(GameState.parse(build_game_state()).object_guard_interface_version, 0)
        for blob in (pb_bytes(21, b'x'), pb_uint(21, 2**32), pb_uint(21, 1)+pb_uint(21, 1)):
            with self.subTest(blob=blob), self.assertRaises(ProtocolError):
                GameState.parse(build_game_state()+blob)
        for kind in (EscortUnit, GuardStructure):
            original = kind(units=(1,), target=2)
            restored = Intent.from_dict(json.loads(json.dumps(original.to_dict())))
            self.assertIsInstance(restored, kind)
            self.assertEqual(tuple(restored.units), (1,))
            self.assertEqual(restored.target, 2)
        args = (TANK, ACTOR_NATIVE, PLAYER_HOUSE, 100, ENEMY_TANK,
                TARGET_NATIVE, PLAYER_HOUSE, 6)
        raw = payloads.guard_object_order(*args)
        expected = dict(zip((1, 5, 6, 7, 3, 8, 9, 10), args)) | {2: 17}
        self.assertEqual({f: v[0][1] for f, v in fmap(raw).items()}, expected)
        self.assertNotIn(4, fmap(raw))
        client = Client()
        client.send_command = Mock()
        client.guard_object_order(*args)
        self.assertEqual(client.send_command.call_args.args[1], raw)
        for i in range(len(args)):
            for bad in (True, -1, 2**32):
                changed = list(args)
                changed[i] = bad
                with self.subTest(i=i, bad=bad), self.assertRaises(InvalidCommand):
                    payloads.guard_object_order(*changed)
        for changes in ({'target': TANK}, {'target_house': ENEMY_HOUSE}, {'target_type': 15}):
            keywords = dict(zip(('pointer','native_id','house_pointer','basis_frame','target',
                                 'target_native_id','target_house','target_type'), args)) | changes
            with self.assertRaises(InvalidCommand):
                payloads.guard_object_order(**keywords)
        text = (f'object_addresses: {TANK} action: UNIT_ACTION_GUARD_OBJECT '
                f'expected_native_id: {ACTOR_NATIVE} expected_house: {PLAYER_HOUSE} basis_frame: 100 '
                f'target_object: {ENEMY_TANK} expected_target_native_id: {TARGET_NATIVE} '
                f'expected_target_house: {PLAYER_HOUSE} expected_target_type: ABSTRACT_TYPE_BUILDING')
        encoded = fmap(subprocess.check_output(['protoc','-I',str(ROOT/'proto'),
                            '--encode=ra2yrproto.commands.UnitOrder',
                            'ra2yrproto/commands_game.proto'], input=text.encode()))
        self.assertEqual(list(packed_varints(encoded.pop(1)[0][1])), [TANK])
        fields = fmap(raw)
        fields.pop(1)
        self.assertEqual(encoded, fields)

    def test_legal_own_targets_and_capability_are_independent(self):
        for kind, target_type in ((EscortUnit, 1), (GuardStructure, 6)):
            initial = state(target_type=target_type)
            plan = self.build(initial, kind=kind)
            self.assertEqual(plan.action, UnitAction.GUARD_OBJECT)
            self.assertIsNone(plan.coordinates)
            self.assertEqual(plan.target_type, target_type)
            self.assertEqual(plan.target_native_id, TARGET_NATIVE)
            self.assertEqual(self.client.state_calls, 0)
            self.assertEqual(self.client.sent, [])
            # Guard/Stop/Attack/actual Target capabilities are absent; own target needs none.
            for changes in ({'version': 0}, {'version': 2},
                            {'actor_changes': {'house': ENEMY_HOUSE}},
                            {'actor_changes': {'object_type': 15}},
                            {'actor_changes': {'mission': Mission.CONSTRUCTION}},
                            {'actor_changes': {'in_limbo': True}},
                            {'actor_changes': {'on_map': False}},
                            {'actor_changes': {'health': 0}},
                            {'actor_changes': {'native_id': None}},
                            {'actor_changes': {'deploying': True}},
                            {'target_changes': {'house': ENEMY_HOUSE}},
                            {'target_changes': {'object_type': 6 if target_type == 1 else 1}},
                            {'target_changes': {'native_id': None}},
                            {'target_changes': {'native_id': 0}},
                            {'target_changes': {'health': 0}},
                            {'target_changes': {'in_limbo': True}},
                            {'target_changes': {'on_map': False}},
                            {'target_changes': {'deploying': True}},
                            {'target_changes': {'undeploying': True}},
                            {'target_changes': {'coordinates': cell_center(8, 3)}}):
                with self.subTest(kind=kind, changes=changes), self.assertRaises(InvalidCommand):
                    self.build(state(target_type=target_type, **changes), kind=kind)
            with self.assertRaises(InvalidCommand):
                Validator(make_map(), allow_foreign=True).check_guard_object(
                    state(target_type=target_type, target_changes={'house': ENEMY_HOUSE}),
                    (TANK,), ENEMY_TANK, target_type)
        self.build(state())
        for units,target in (((),self.target), ((self.actor,self.actor),self.target),
                             ((self.actor,),self.actor), ((self.actor,),True)):
            with self.assertRaises(InvalidCommand):
                self.executor.plan(EscortUnit(units=units,target=target),state())

    def test_freeze_before_read_rejects_rebinding_and_transformation(self):
        initial = state()
        for side in ('actor_changes','target_changes'):
            for changes in ({'pointer': 0xC1, 'object_type': 6, 'native_id': ACTOR_NATIVE+1},
                            {'type_pointer': 0xABCD}, {'house': ENEMY_HOUSE},
                            {'native_id': 123}, {'native_id': None}):
                self.build(initial)
                fresh = state(101, **{side: changes})
                observer = Observer(self.client, identity=self.identity, map_data=make_map())
                def refresh():
                    observer.absorb(fresh)
                    return fresh
                self.executor._read = refresh
                with self.subTest(side=side, changes=changes), self.assertRaises(InvalidCommand):
                    self.executor.execute(self.intent, initial)
                self.assertEqual(self.client.sent, [])
        for frame in (99,251):
            self.build(initial)
            self.executor._read = lambda: state(frame)
            with self.assertRaises(InvalidCommand):
                self.executor.execute(self.intent, initial)
            self.assertEqual(self.client.sent, [])

    def test_input_only_no_attack_target_or_destination_fallback(self):
        for kind, target_type in ((EscortUnit,1), (GuardStructure,6)):
            plan = self.build(state(target_type=target_type), kind=kind)
            after = state(101, target_type=target_type, events=(event(),),
                          actor_changes={'mission': Mission.MOVE, 'destination': cell_center(2,2)},
                          target_changes={'coordinates': cell_center(4,4)})
            self.assertTrue(plan.verify(after))
            self.assertEqual(plan.observations['native_input'], 'observed')
            self.assertEqual(plan.observations['input_observed_frame'], 101)
            self.assertNotIn('actual_target', plan.observations)
            self.assertFalse(plan.verify(replace(after, _native_events=())))

    def test_old_or_wrong_events_and_changed_bindings_never_confirm(self):
        initial = state(events=(event(frame=100),))
        plan = self.build(initial)
        old = event(frame=120, source='do', executed=True)
        self.assertFalse(plan.verify(state(101, events=(old,))))
        for changes in ({'frame':99}, {'actor': ACTOR_NATIVE+1}, {'target': TARGET_NATIVE+1},
                        {'rtti':11}, {'actor_rtti':1}, {'house':1}, {'mission':1},
                        {'planning':True}, {'destination':(1001,11)},
                        {'follow':(TARGET_NATIVE,52)}, {'event_type':5}):
            plan = self.build(state())
            with self.subTest(changes=changes):
                self.assertFalse(plan.verify(state(101,events=(event(**changes),))))
        for side in ('actor_changes','target_changes'):
            for changes in ({'native_id':123}, {'type_pointer':0xABCD}, {'house':ENEMY_HOUSE},
                            {'on_map':False}, {'health':0}, {'deploying':True}):
                plan=self.build(state())
                self.assertFalse(plan.verify(state(101,events=(event(),),**{side:changes})))
        plan=self.build(state())
        # Null destination/follow may have nonzero ID, and event Frame may be scheduled ahead.
        self.assertTrue(plan.verify(state(101,events=(event(frame=120,destination=(123,0),
                                                           follow=(456,0)),))))

    def test_execute_one_input_and_unknown_keeps_plan(self):
        initial=state()
        self.build(initial,state(101,events=(event(),)))
        outcome=self.executor.execute(self.intent,initial)
        self.assertEqual(outcome.evidence,'native_input_observed')
        self.assertEqual(outcome.plan.verify_basis,'native_input')
        self.assertEqual(len(self.client.sent),1)
        self.build(initial,state(101),state(103),max_wait_frames=2)
        with self.assertRaises(Timeout) as caught:
            self.executor.execute(self.intent,initial)
        self.assertEqual(len(self.client.sent),1)
        self.assertTrue(caught.exception.plan.verify(state(104,events=(event(frame=104),))))
        self.assertEqual(len(self.client.sent),1)


class TestObjectGuardTactics(unittest.TestCase):
    def build(self, *states, tactic='escort_unit', max_wait_frames=45):
        target_type=1 if tactic=='escort_unit' else 6
        self.client=GuardObjectClient(states or (state(target_type=target_type),
                            state(101,target_type=target_type,events=(event(),))))
        self.observer=Observer(self.client,map_data=make_map())
        self.obs=self.observer.poll()
        self.actor=self.observer.identity.agent_id(TANK)
        self.target=self.observer.identity.agent_id(ENEMY_TANK)
        self.registry=TacticRegistry().load(t for t in TACTICS
                              if t.info.name in ('escort_unit','guard_structure'))
        executor=Executor(self.client,self.observer.identity,validator=Validator(make_map()),
                          read_state=lambda:self.observer.poll().state,
                          sleep=lambda _:self.client.advance(),max_wait_frames=max_wait_frames)
        self.layer=MicroLayer(self.observer,registry=self.registry,executor=executor)
        self.commander=Commander(self.layer,self.observer)
        self.request=CallRequest(tactic=tactic,units=(self.actor,),params={'target':self.target})

    def test_pool_and_squad_target_outside_scope_single_settlement(self):
        for tactic in ('escort_unit','guard_structure'):
            self.build(tactic=tactic)
            intents=self.registry.run(tactic,observation=self.obs,
                       subject=UnitPool(self.obs,self.observer.identity),
                       params=self.request.params,frame=100)
            self.assertEqual(intents[0].target,self.target)
            accepted=self.commander.call([self.request],self.obs)[0]
            self.assertTrue(accepted.accepted,accepted.error)
            self.assertEqual(self.layer.squads()[0].agents(),(self.actor,))
            self.assertNotIn(self.target,self.layer.squads()[0].agents())
            intent=type(intents[0])(units=(self.actor,),target=self.target,scope=self.layer.squads()[0].intent.scope)
            check_command_scope(intent,(self.actor,))
            self.assertEqual(self.layer.tick(self.obs)[0].evidence,'native_input_observed')
            self.assertEqual(self.layer.squads(),())
            self.assertEqual(self.layer.completed[-1]['completion_basis'],{self.actor:'operation_observed'})
            text=self.commander.status(self.observer.poll()).render()
            self.assertIn('operation_observed',text)
            self.assertIn('native_input=observed',text)
            self.layer.tick(self.observer.poll())
            self.assertEqual(len(self.client.sent),1)

    def test_cards_and_call_gates_parameters_empty_units_no_map(self):
        for version in (0,2):
            self.build(state(version=version))
            self.assertEqual(self.registry.cards(Mode.MATCH,self.obs,
                                      UnitPool(self.obs,self.observer.identity)),[])
            self.assertFalse(self.commander.call([self.request],self.obs)[0].accepted)
        self.build()
        for request,obs in ((replace(self.request,units=()),self.obs),
                            (replace(self.request,params={}),self.obs),
                            (replace(self.request,params={'target':True}),self.obs),
                            (replace(self.request,params={'target':self.target,'cell':[2,2]}),self.obs),
                            (self.request,replace(self.obs,map_data=None)),
                            (replace(self.request,tactic='guard_structure'),self.obs)):
            with self.subTest(request=request):
                self.assertFalse(self.commander.call([request],obs)[0].accepted)
        self.assertEqual(self.client.sent,[])

    def test_unknown_late_input_or_cancel_never_resubmits_or_stops(self):
        for cancel in (False,True):
            self.build(state(),state(101),state(103),max_wait_frames=2)
            accepted=self.commander.call([self.request],self.obs)[0]
            self.assertTrue(accepted.accepted)
            self.assertEqual(self.layer.tick(self.obs),[])
            self.layer.tick(self.observer.poll())
            self.assertEqual(len(self.client.sent),1)
            self.assertIn('结果未知',self.commander.status(self.observer.poll()).render())
            if cancel:
                self.assertTrue(self.layer.cancel(accepted.intent_id))
            self.client.timeline.append(state(104,events=(event(frame=104),)))
            self.client.advance()
            self.layer.tick(self.observer.poll())
            self.assertEqual(self.layer.squads(),())
            self.assertEqual(len(self.client.sent),1)
            if not cancel:
                self.assertEqual(self.layer.completed[-1]['completion_basis'],{self.actor:'operation_observed'})


class TestObjectGuardNativePolicy(unittest.TestCase):
    def test_compiled_policy_checks_own_live_fixed_target_and_map(self):
        patch=(ROOT/'engine/ra2yrcpp/patches/object-guard-v1-engine.patch').read_text()
        section=patch.split('diff --git a/src/ra2/guard_object_policy.hpp b/src/ra2/guard_object_policy.hpp\n',1)[1]
        section=section.split('\ndiff --git ',1)[0]
        header='\n'.join(line[1:] for line in section.splitlines()
                          if line.startswith('+') and not line.startswith('+++'))+'\n'
        with tempfile.TemporaryDirectory(prefix='ra2-object-guard-') as directory:
            root=Path(directory)
            (root/'guard_object_policy.hpp').write_text(header)
            (root/'check.cpp').write_text('''#include "guard_object_policy.hpp"
#include <cassert>
int main() {
  using namespace ra2::guard_object_policy;
  Target base{0xFFFFFE80u,8192,1,true,true,false,true};
  assert(matches(base,base.native_id,base.house,1));
  auto building=base; building.type=6;
  assert(matches(building,base.native_id,base.house,6));
  Target cases[]={{0,8192,1,true,true,false,true},{1,0,1,true,true,false,true},
    {1,8192,15,true,true,false,true},{1,8192,1,false,true,false,true},
    {1,8192,1,true,false,false,true},{1,8192,1,true,true,true,true},
    {1,8192,1,true,true,false,false}};
  for(auto t:cases) assert(!eligible(t));
  assert(!matches(base,base.native_id-1,base.house,1));
  assert(!matches(base,base.native_id,base.house+1,1));
  assert(!matches(base,base.native_id,base.house,6));
}
''')
            subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror',
                            str(root/'check.cpp'),'-o',str(root/'check')],check=True,
                           capture_output=True,text=True)
            subprocess.run([str(root/'check')],check=True)


if __name__=='__main__':
    unittest.main()
