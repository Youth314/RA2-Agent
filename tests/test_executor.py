"""L0 执行器的测试。

执行器是纯逻辑，故用假客户端离线测试：选路（意图到命令的对应）、发送前校验、
按帧验证、失焦检测、错误归一化。真实生效延迟的实测见
`.agents/notes/命令能力测绘结果.md#命令生效延迟`。
"""
import json
import os
import tempfile
import unittest

from ra2agent.client import CommandResult
from ra2agent.constants import (AbstractType, LandType, Mission, NetworkEvent,
                                UnitAction)
from ra2agent.errors import (CommandFailed, GameNotResponding, InvalidCommand,
                             Timeout)
from ra2agent.executor import Executor, reason_for
from ra2agent.identity import IdentityTable
from ra2agent.intents import (Attack, DecisionLog, Deploy, Hold, Intent, MoveTo,
                              Place, Produce, Sell, Stance)
from ra2agent.state import GameState, MapData, TypeTable, cell_center
from ra2agent.validate import Validator
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_factory,
                            build_game_state, build_house, build_map_soa,
                            build_object, build_type_table)

TANK = 0xA1
ENEMY_TANK = 0xB1
MCV = 0xA2
BUILDING = 0xA3
PLANT = 0xA4
PENDING = 0xA5
SIDE = 8


# ---------------------------------------------------------------- 构造
def make_map(side=SIDE):
    """一张 side×side、全部已探索且为 Clear 的地图。"""
    cells = side * side
    return MapData.parse(build_map_soa(width=side, height=side,
                                       shrouded=[0] * cells,
                                       land=[LandType.CLEAR] * cells))


def at(cell):
    """格中心的世界坐标。"""
    return cell[0] * 256 + 128, cell[1] * 256 + 128


def make_state(frame=100, objects=(), factories=(), houses=None):
    return GameState.parse(build_game_state(
        frame=frame,
        houses=houses or [build_house(PLAYER_HOUSE, current_player=True),
                          build_house(ENEMY_HOUSE)],
        objects=list(objects), factories=list(factories)))


def tank(pointer, cell, mission=Mission.GUARD, house=PLAYER_HOUSE, **kwargs):
    x, y = at(cell)
    return build_object(pointer, house=house, object_type=AbstractType.UNIT,
                        mission=mission, x=x, y=y, **kwargs)


def building(pointer, cell, mission=Mission.GUARD, house=PLAYER_HOUSE, **kwargs):
    x, y = at(cell)
    return build_object(pointer, house=house, object_type=AbstractType.BUILDING,
                        mission=mission, x=x, y=y, **kwargs)


class JumpingClock:
    """每次读数跳一大步的假时钟。"""

    def __init__(self, step=100.0):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


class FakeClient:
    """按时间线返回状态的假客户端，记录发出的命令。

    `get_state` 只回报当前时刻的状态，帧由 `advance` 推进——执行器的 `sleep`
    被接到 `advance` 上，故「睡一会儿」即「游戏走一步」。时间线走完即帧冻结。
    """

    def __init__(self, states, code=None, error=""):
        self.timeline = list(states)
        self.index = 0
        self.state_calls = 0
        self.sent = []
        self.code = code
        self.error = error

    @property
    def current(self):
        """当前时刻的状态。"""
        return self.timeline[self.index]

    def advance(self, steps=1):
        """把时间线向前推进，不越过最后一帧。"""
        self.index = min(self.index + steps, len(self.timeline) - 1)

    def get_state(self):
        self.state_calls += 1
        return self.current

    def _reply(self, command):
        return CommandResult(type=command, payload=b"", code=self.code,
                             error=self.error)

    def unit_order(self, units, action, target_object=None, coordinates=None):
        self.sent.append(("UnitOrder", tuple(units), action, target_object,
                          coordinates))
        return self._reply("UnitOrder")

    def click_event(self, units, event):
        self.sent.append(("ClickEvent", tuple(units), event))
        return self._reply("ClickEvent")

    def produce_order(self, entry):
        self.sent.append(("ProduceOrder", entry.name))
        return self._reply("ProduceOrder")

    def place_building(self, pointer, coordinates):
        self.sent.append(("PlaceBuilding", pointer, coordinates))
        return self._reply("PlaceBuilding")


class ExecutorCase(unittest.TestCase):
    """搭好地图、校验器、标识表与执行器的公共部分。"""

    def build(self, *states, types=None, log=None, **kwargs):
        """用状态时间线建立假客户端与执行器；标识表取自第一帧。"""
        self.client = FakeClient(states, **kwargs.pop("client_kwargs", {}))
        self.identity = IdentityTable()
        self.identity.update(states[0])
        self.executor = Executor(self.client, self.identity, types=types, log=log,
                                 validator=Validator(make_map()),
                                 sleep=lambda _: self.client.advance(), **kwargs)
        return self.executor

    def agent(self, pointer):
        """对象指针的 Agent 侧 id。"""
        return self.identity.agent_id(pointer)


# ---------------------------------------------------------------- 选路
class TestRouting(ExecutorCase):
    """同一意图在任何局面下都走同一条命令。"""

    def setUp(self):
        self.state = make_state(objects=[
            tank(TANK, (1, 1)),
            building(BUILDING, (3, 3)),
            building(PLANT, (4, 4), mission=Mission.CONSTRUCTION),
            tank(MCV, (5, 5)),
        ])
        self.build(self.state)
        self.types = TypeTable.parse(build_type_table([
            ("GAPOWR", 800, 3, 0x700, AbstractType.BUILDINGTYPE)]))

    def test_plan_does_not_touch_the_client(self):
        self.executor.plan(MoveTo(units=(self.agent(TANK),), cell=(2, 2)),
                           self.state)
        self.assertEqual(self.client.sent, [])
        self.assertEqual(self.client.state_calls, 0)

    def test_aggressive_moves_with_attack_move(self):
        plan = self.executor.plan(
            MoveTo(units=(self.agent(TANK),), cell=(2, 2),
                   stance=Stance.AGGRESSIVE), self.state)
        self.assertEqual((plan.command, plan.action),
                         ("UnitOrder", UnitAction.ATTACK_MOVE))
        self.assertEqual(plan.pointers, (TANK,))
        self.assertEqual(plan.coordinates, cell_center(2, 2))

    def test_passive_moves_with_move(self):
        plan = self.executor.plan(
            MoveTo(units=(self.agent(TANK),), cell=(2, 2), stance=Stance.PASSIVE),
            self.state)
        self.assertEqual((plan.command, plan.action),
                         ("UnitOrder", UnitAction.MOVE))

    def test_hold_stance_stops_without_coordinates(self):
        plan = self.executor.plan(
            MoveTo(units=(self.agent(TANK),), cell=(2, 2), stance=Stance.HOLD),
            self.state)
        self.assertEqual((plan.command, plan.action),
                         ("UnitOrder", UnitAction.STOP))
        self.assertIsNone(plan.coordinates)

    def test_hold_intent_stops(self):
        plan = self.executor.plan(Hold(units=(self.agent(TANK),)), self.state)
        self.assertEqual((plan.command, plan.action),
                         ("UnitOrder", UnitAction.STOP))

    def test_attack_targets_object(self):
        plan = self.executor.plan(
            Attack(units=(self.agent(TANK),), target=self.agent(BUILDING)),
            self.state)
        self.assertEqual((plan.command, plan.action),
                         ("UnitOrder", UnitAction.ATTACK))
        self.assertEqual(plan.target, BUILDING)

    def test_sell_goes_through_click_event(self):
        # 刚放置的建筑处于 Mission_Construction，UnitOrder 会拒绝
        plan = self.executor.plan(Sell(buildings=(self.agent(PLANT),)), self.state)
        self.assertEqual((plan.command, plan.action),
                         ("ClickEvent", NetworkEvent.SELL))
        self.assertEqual(plan.pointers, (PLANT,))

    def test_deploy_goes_through_click_event(self):
        plan = self.executor.plan(Deploy(units=(self.agent(MCV),)), self.state)
        self.assertEqual((plan.command, plan.action),
                         ("ClickEvent", NetworkEvent.DEPLOY))

    def test_place_uses_cell_center(self):
        plan = self.executor.plan(
            Place(building=self.agent(BUILDING), cell=(2, 4)), self.state)
        self.assertEqual(plan.command, "PlaceBuilding")
        self.assertEqual(plan.pointers, (BUILDING,))
        self.assertEqual(plan.coordinates, cell_center(2, 4))

    def test_multi_unit_move_is_one_command(self):
        # 实测一条命令带多个 object_addresses 可全部生效
        plan = self.executor.plan(
            MoveTo(units=(self.agent(TANK), self.agent(MCV)), cell=(2, 2)),
            self.state)
        self.assertEqual(plan.pointers, (TANK, MCV))

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(Intent(), self.state)
        self.assertIn("不认识", str(ctx.exception))

    def test_unknown_stance_is_rejected(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(MoveTo(units=(self.agent(TANK),), stance="berserk"),
                               self.state)
        self.assertIn("stance", str(ctx.exception))


class TestProduceRouting(ExecutorCase):
    def setUp(self):
        self.state = make_state(factories=[build_factory(PLAYER_HOUSE, 0x900)])
        self.types = TypeTable.parse(build_type_table([
            ("GAPOWR", 800, 3, 0x700, AbstractType.BUILDINGTYPE)]))
        self.build(self.state, types=self.types)

    def test_resolves_type_entry(self):
        plan = self.executor.plan(Produce(type_pointer=0x700, type_name="GAPOWR"),
                                  self.state)
        self.assertEqual(plan.command, "ProduceOrder")
        self.assertIsNone(plan.action)
        self.assertEqual(plan.object_type.pointer, 0x700)
        self.assertEqual(plan.object_type.array_index, 3)

    def test_without_type_table_is_rejected(self):
        executor = Executor(self.client, self.identity, sleep=lambda _: None)
        with self.assertRaises(InvalidCommand) as ctx:
            executor.plan(Produce(type_pointer=0x700), self.state)
        self.assertIn("类型表", str(ctx.exception))

    def test_with_unknown_type_is_rejected(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(Produce(type_pointer=0xDEAD, type_name="NOPE"),
                               self.state)
        self.assertIn("NOPE", str(ctx.exception))


# ---------------------------------------------------------------- 校验
class TestValidation(ExecutorCase):
    def setUp(self):
        self.state = make_state(objects=[
            tank(TANK, (1, 1)),
            tank(ENEMY_TANK, (2, 2), house=ENEMY_HOUSE),
            building(PLANT, (4, 4), mission=Mission.CONSTRUCTION),
        ])
        self.build(self.state)

    def test_rejects_foreign_object(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(Sell(buildings=(self.agent(ENEMY_TANK),)), self.state)
        self.assertIn("不是己方", str(ctx.exception))
        self.assertEqual(self.client.sent, [])

    def test_rejects_unobserved_agent_id(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(Hold(units=(9999,)), self.state)
        self.assertIn("标识表", str(ctx.exception))

    def test_rejects_unit_missing_from_state(self):
        stale = make_state(objects=[tank(TANK, (1, 1))])
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(Hold(units=(self.agent(PLANT),)), stale)
        self.assertIn("不在当前状态", str(ctx.exception))

    def test_rejects_target_missing_from_state(self):
        stale = make_state(objects=[tank(TANK, (1, 1))])
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(Attack(units=(self.agent(TANK),),
                                      target=self.agent(PLANT)), stale)
        self.assertIn("不在当前状态", str(ctx.exception))

    def test_rejects_empty_object_list(self):
        with self.assertRaises(InvalidCommand):
            self.executor.plan(Sell(buildings=()), self.state)

    def test_rejects_coordinates_without_map(self):
        executor = Executor(self.client, self.identity, sleep=lambda _: None)
        with self.assertRaises(InvalidCommand) as ctx:
            executor.plan(MoveTo(units=(self.agent(TANK),), cell=(2, 2)), self.state)
        self.assertIn("地图", str(ctx.exception))

    def test_rejects_out_of_map_cell(self):
        with self.assertRaises(InvalidCommand):
            self.executor.plan(MoveTo(units=(self.agent(TANK),), cell=(99, 99)),
                               self.state)

    def test_rejects_terminal_intent(self):
        for state in ("satisfied", "failed", "expired", "superseded"):
            intent = Hold(units=(self.agent(TANK),))
            intent.state = state
            with self.subTest(state=state):
                with self.assertRaises(InvalidCommand) as ctx:
                    self.executor.plan(intent, self.state)
                self.assertIn("终态", str(ctx.exception))

    def test_rejects_expired_intent(self):
        intent = Hold(units=(self.agent(TANK),), created_frame=50, ttl_frames=10)
        with self.assertRaises(InvalidCommand) as ctx:
            self.executor.plan(intent, self.state)
        self.assertIn("过期", str(ctx.exception))

    def test_accepts_intent_within_ttl(self):
        intent = Hold(units=(self.agent(TANK),), created_frame=95, ttl_frames=10)
        self.executor.plan(intent, self.state)


# ---------------------------------------------------------------- 生效判据
class TestVerification(ExecutorCase):
    def setUp(self):
        self.state = make_state(objects=[
            tank(TANK, (1, 1)),
            building(PLANT, (4, 4), mission=Mission.CONSTRUCTION),
            tank(MCV, (5, 5)),
            building(PENDING, (0, 0), in_limbo=True),
        ], factories=[build_factory(PLAYER_HOUSE, 0x900)])
        self.types = TypeTable.parse(build_type_table([
            ("GAPOWR", 800, 3, 0x700, AbstractType.BUILDINGTYPE)]))
        self.build(self.state, types=self.types)

    def test_move_judged_by_destination(self):
        plan = self.executor.plan(
            MoveTo(units=(self.agent(TANK),), cell=(2, 2)), self.state)
        self.assertFalse(plan.verify(self.state))
        self.assertTrue(plan.verify(make_state(
            objects=[tank(TANK, (1, 1), destination=at((2, 2)))])))

    def test_move_needs_every_unit(self):
        # 只要有一个对象没到位，整条命令就不算生效
        plan = self.executor.plan(
            MoveTo(units=(self.agent(TANK), self.agent(MCV)), cell=(2, 2)),
            self.state)
        partial = make_state(objects=[
            tank(TANK, (1, 1), destination=at((2, 2))), tank(MCV, (5, 5))])
        self.assertFalse(plan.verify(partial))

    def test_stop_judged_by_mission(self):
        plan = self.executor.plan(Hold(units=(self.agent(TANK),)), self.state)
        self.assertFalse(plan.verify(self.state))
        self.assertTrue(plan.verify(make_state(
            objects=[tank(TANK, (1, 1), mission=Mission.STOP)])))

    def test_attack_judged_by_mission(self):
        plan = self.executor.plan(
            Attack(units=(self.agent(TANK),), target=self.agent(PLANT)), self.state)
        self.assertFalse(plan.verify(self.state))
        self.assertTrue(plan.verify(make_state(
            objects=[tank(TANK, (1, 1), mission=Mission.ATTACK)])))

    def test_deploy_judged_by_pointer_or_flag(self):
        plan = self.executor.plan(Deploy(units=(self.agent(MCV),)), self.state)
        self.assertFalse(plan.verify(self.state))
        self.assertTrue(plan.verify(make_state(
            objects=[tank(MCV, (5, 5), deployed=True)])))
        self.assertTrue(plan.verify(make_state(objects=[])))

    def test_sell_judged_by_selling_mission(self):
        plan = self.executor.plan(Sell(buildings=(self.agent(PLANT),)), self.state)
        self.assertFalse(plan.verify(self.state))
        self.assertTrue(plan.verify(make_state(
            objects=[building(PLANT, (4, 4), mission=Mission.SELLING)])))
        self.assertTrue(plan.verify(make_state(objects=[])))

    def test_place_judged_by_position(self):
        plan = self.executor.plan(
            Place(building=self.agent(PENDING), cell=(2, 3)), self.state)
        self.assertFalse(plan.verify(self.state))
        self.assertTrue(plan.verify(make_state(
            objects=[building(PENDING, (2, 3), in_limbo=False)])))

    def test_produce_judged_by_factory_change(self):
        plan = self.executor.plan(Produce(type_pointer=0x700), self.state)
        self.assertFalse(plan.verify(self.state))
        busy = make_state(factories=[build_factory(PLAYER_HOUSE, 0x900, timer=5)])
        self.assertTrue(plan.verify(busy))

    def test_plan_carries_decision_facts(self):
        plan = self.executor.plan(Hold(units=(self.agent(TANK),)), self.state)
        self.assertEqual(plan.facts["objects"][str(TANK)], [1, 1])
        self.assertEqual(plan.facts["frame"], 100)
        self.assertIn("UnitOrder", plan.describe())
        self.assertIn("STOP", plan.describe())


# ---------------------------------------------------------------- 执行
class TestExecute(ExecutorCase):
    def setUp(self):
        self.first = make_state(objects=[tank(TANK, (1, 1))])

    def move_intent(self):
        return MoveTo(units=(self.agent(TANK),), cell=(2, 2))

    def test_success_waits_for_state(self):
        # 命令在第 100 帧发出，目标格到第 103 帧才写进 destination
        states = [make_state(frame=101, objects=[tank(TANK, (1, 1))]),
                  make_state(frame=102, objects=[tank(TANK, (1, 1))]),
                  make_state(frame=103,
                             objects=[tank(TANK, (1, 1), destination=at((2, 2)))])]
        executor = self.build(*states)
        outcome = executor.execute(self.move_intent(), self.first)
        self.assertEqual(outcome.frames_waited, 2)
        self.assertEqual(outcome.polls, 3)
        self.assertEqual(outcome.state.frame, 103)
        self.assertEqual(outcome.kind, "move_to")
        self.assertEqual(len(self.client.sent), 1)
        command, pointers, action, target, coordinates = self.client.sent[0]
        self.assertEqual(command, "UnitOrder")
        self.assertEqual(pointers, (TANK,))
        self.assertEqual(action, UnitAction.ATTACK_MOVE)
        self.assertIsNone(target)
        self.assertEqual(coordinates, cell_center(2, 2))
        self.assertIn("move_to#", outcome.describe())

    def test_success_at_once(self):
        state = make_state(objects=[tank(TANK, (1, 1), destination=at((2, 2)))])
        executor = self.build(state)
        outcome = executor.execute(self.move_intent(), state)
        self.assertEqual(outcome.frames_waited, 0)
        self.assertEqual(outcome.polls, 1)

    def test_server_failure_is_normalized(self):
        executor = self.build(self.first, client_kwargs={
            "code": 2, "error": "Object has illegal mission: 18"})
        with self.assertRaises(CommandFailed) as ctx:
            executor.execute(Hold(units=(self.agent(TANK),)), self.first)
        self.assertEqual(ctx.exception.reason, "illegal_mission")
        self.assertEqual(ctx.exception.command_type, "UnitOrder")
        self.assertIn("UnitOrder", str(ctx.exception))

    def test_frames_running_out_is_timeout(self):
        states = [make_state(frame=100 + i, objects=[tank(TANK, (1, 1))])
                  for i in range(10)]
        executor = self.build(*states, max_wait_frames=4)
        with self.assertRaises(Timeout) as ctx:
            executor.execute(self.move_intent(), states[0])
        self.assertIn("4 帧", str(ctx.exception))

    def test_frozen_frame_is_not_responding(self):
        # 假时钟让「帧停了 1.5 秒」立刻成立，免得测试真等
        executor = self.build(self.first, clock=JumpingClock(step=1.0))
        with self.assertRaises(GameNotResponding) as ctx:
            executor.execute(self.move_intent(), self.first)
        self.assertIn("失焦", str(ctx.exception))

    def test_real_time_budget_is_enforced(self):
        states = [make_state(frame=100 + i, objects=[tank(TANK, (1, 1))])
                  for i in range(6)]
        executor = self.build(*states, timeout_s=10, clock=JumpingClock())
        with self.assertRaises(Timeout) as ctx:
            executor.execute(self.move_intent(), states[0])
        self.assertIn("秒", str(ctx.exception))

    def test_custom_reader_is_used(self):
        reads = []
        states = [self.first,
                  make_state(frame=101,
                             objects=[tank(TANK, (1, 1), destination=at((2, 2)))])]
        executor = self.build(
            *states,
            read_state=lambda: reads.append(1) or self.client.get_state())
        executor.execute(self.move_intent(), self.first)
        self.assertTrue(reads)

    def test_click_event_is_delivered(self):
        state = make_state(objects=[
            building(PLANT, (4, 4), mission=Mission.CONSTRUCTION)])
        executor = self.build(state, make_state(frame=101, objects=[
            building(PLANT, (4, 4), mission=Mission.SELLING)]))
        executor.execute(Sell(buildings=(self.agent(PLANT),)), state)
        self.assertEqual(self.client.sent[0],
                         ("ClickEvent", (PLANT,), NetworkEvent.SELL))

    def test_place_building_is_delivered(self):
        state = make_state(objects=[building(PENDING, (0, 0), in_limbo=True)])
        executor = self.build(state, make_state(
            frame=101, objects=[building(PENDING, (2, 3), in_limbo=False)]))
        executor.execute(Place(building=self.agent(PENDING), cell=(2, 3)), state)
        self.assertEqual(self.client.sent[0],
                         ("PlaceBuilding", PENDING, cell_center(2, 3)))

    def test_produce_order_is_delivered(self):
        types = TypeTable.parse(build_type_table(
            [("GAPOWR", 800, 3, 0x700, AbstractType.BUILDINGTYPE)]))
        state = make_state(factories=[build_factory(PLAYER_HOUSE, 0x900)])
        executor = self.build(state, make_state(
            frame=101,
            factories=[build_factory(PLAYER_HOUSE, 0x900, timer=3)]), types=types)
        executor.execute(Produce(type_pointer=0x700), state)
        self.assertEqual(self.client.sent[0], ("ProduceOrder", "GAPOWR"))

    def test_deploy_is_delivered(self):
        state = make_state(objects=[tank(MCV, (5, 5))])
        executor = self.build(state, make_state(
            frame=101, objects=[building(BUILDING, (5, 5))]))
        executor.execute(Deploy(units=(self.agent(MCV),)), state)
        self.assertEqual(self.client.sent[0],
                         ("ClickEvent", (MCV,), NetworkEvent.DEPLOY))


class TestReasonFor(unittest.TestCase):
    def test_known_messages(self):
        cases = {
            "object not found": "object_missing",
            "Object has illegal mission: 18": "illegal_mission",
            "invalid unit action": "action_unimplemented",
            "Proximity check failed": "placement_blocked",
            "unbuildable": "unbuildable",
        }
        for message, reason in cases.items():
            with self.subTest(message=message):
                self.assertEqual(reason_for(message), reason)

    def test_unknown_message_falls_through(self):
        self.assertEqual(reason_for("某种未记录的措辞"), "unknown")
        self.assertEqual(reason_for(""), "unknown")


# ---------------------------------------------------------------- 决策日志
class TestDecisionLog(ExecutorCase):
    def setUp(self):
        self.first = make_state(objects=[tank(TANK, (1, 1))])
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.log = DecisionLog(os.path.join(self.directory.name, "decisions.jsonl"))
        self.addCleanup(self.log.close)

    def read_log(self):
        with open(self.log.path, encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_records_send_and_success(self):
        state = make_state(frame=101,
                           objects=[tank(TANK, (1, 1), destination=at((2, 2)))])
        executor = self.build(self.first, state, log=self.log)
        intent = MoveTo(units=(self.agent(TANK),), cell=(2, 2), layer=1,
                        issuer="script")
        executor.execute(intent, self.first)
        entries = self.read_log()
        self.assertEqual([e["event"] for e in entries],
                         ["command_sent", "command_executed"])
        self.assertEqual(entries[0]["intent_id"], intent.id)
        self.assertEqual(entries[0]["layer"], 1)
        self.assertEqual(entries[1]["frame"], 101)
        self.assertEqual(entries[1]["detail"]["polls"], 2)
        self.assertEqual(entries[1]["detail"]["frames_waited"], 1)

    def test_records_local_rejection(self):
        executor = self.build(self.first, log=self.log)
        with self.assertRaises(InvalidCommand):
            executor.execute(Hold(units=(9999,)), self.first)
        self.assertEqual([e["event"] for e in self.read_log()],
                         ["command_rejected"])
        self.assertEqual(self.client.sent, [])

    def test_records_server_failure(self):
        executor = self.build(self.first, log=self.log,
                              client_kwargs={"code": 2, "error": "object not found"})
        with self.assertRaises(CommandFailed):
            executor.execute(Hold(units=(self.agent(TANK),)), self.first)
        entries = self.read_log()
        self.assertEqual([e["event"] for e in entries],
                         ["command_sent", "command_failed"])
        self.assertEqual(entries[1]["detail"]["reason"], "object_missing")

    def test_records_unverified_command(self):
        executor = self.build(self.first, log=self.log,
                              clock=JumpingClock(step=1.0))
        with self.assertRaises(GameNotResponding):
            executor.execute(Hold(units=(self.agent(TANK),)), self.first)
        self.assertEqual([e["event"] for e in self.read_log()],
                         ["command_sent", "command_unverified"])


if __name__ == "__main__":
    unittest.main()
