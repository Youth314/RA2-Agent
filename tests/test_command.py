"""指挥层的测试。

四个工具的行为：读局势（含事件只报一次）、读卡片（按局面筛）、下达（受理与拒绝
各条独立）、撤销。全是离线假件，不碰游戏。
"""
import unittest

from ra2agent.command import CallRequest, Commander, UnitPool
from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.errors import TacticError
from ra2agent.events import EventKind, EventLog
from ra2agent.executor import CommandPlan, ExecutionOutcome
from ra2agent.client import CommandResult
from ra2agent.identity import IdentityTable
from ra2agent.intents import IntentState, Scope, TacticCall
from ra2agent.micro import MicroLayer, UnitMode
from ra2agent.observation import Observation
from ra2agent.state import GameState, MapData
from ra2agent.tactics import Level, Tactic, TacticInfo, TacticPolicy, TacticRegistry
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_game_state,
                            build_house, build_map_soa, build_object)

SIDE = 9
ALLY_A = 0xA1
ALLY_B = 0xA2
ENEMY = 0xB1


def make_map():
    cells = SIDE * SIDE
    return MapData.parse(build_map_soa(width=SIDE, height=SIDE,
                                       shrouded=[0] * cells,
                                       land=[LandType.CLEAR] * cells))


MAP = make_map()


def at(cell):
    return cell[0] * 256 + 128, cell[1] * 256 + 128


def make_state(frame=100, objects=()):
    return GameState.parse(build_game_state(
        frame=frame,
        houses=[build_house(PLAYER_HOUSE, current_player=True),
                build_house(ENEMY_HOUSE)],
        objects=list(objects)))


def tank(pointer, cell, house=PLAYER_HOUSE, mission=Mission.GUARD, **kwargs):
    x, y = at(cell)
    return build_object(pointer, house=house, object_type=AbstractType.UNIT,
                        mission=mission, x=x, y=y, **kwargs)


class FakeExecutor:
    """记录意图并直接成功的假执行器。"""

    def __init__(self):
        self.calls = []
        self.error = None

    def execute(self, intent, state):
        self.calls.append(intent)
        if self.error is not None:
            raise self.error
        plan = CommandPlan(kind=intent.kind, command="UnitOrder", action=None,
                           verify=lambda current: True)
        return ExecutionOutcome(
            intent_id=intent.id, kind=intent.kind, plan=plan, frames_waited=0,
            polls=1, state=state,
            result=CommandResult(type="UnitOrder", payload=b"", code=None, error=""))


class FakeObserver:
    def __init__(self, state, map_data=None):
        self.events = EventLog()
        self.identity = IdentityTable()
        self.identity.update(state)
        self.map_data = map_data if map_data else MAP
        self.types = None
        self.client = None
        self.observation = None

    def poll(self):
        return self.observation


class Case(unittest.TestCase):
    def build(self, state, observation=None, registry=None, **kwargs):
        self.observer = FakeObserver(state)
        self.executor = FakeExecutor()
        self.registry = registry or TacticRegistry().load_builtin()
        self.layer = MicroLayer(self.observer, self.registry, self.executor,
                                sleep=lambda _: None, **kwargs)
        self.commander = Commander(self.layer, self.observer)
        self.state = state
        self.observation = observation or Observation(
            frame=state.frame, house=state.player_house(),
            own=tuple(o for o in state.objects if o.house == PLAYER_HOUSE),
            visible_enemies=(), neutral=(), state=state, map_data=MAP)
        self.observer.observation = self.observation
        return self.commander

    def agent(self, pointer):
        return self.observer.identity.agent_id(pointer)

    def tick(self, state):
        self.observation = Observation(
            frame=state.frame, house=state.player_house(),
            own=tuple(o for o in state.objects if o.house == PLAYER_HOUSE),
            visible_enemies=(), neutral=(), state=state, map_data=MAP)
        self.observer.observation = self.observation
        return self.layer.tick(self.observation)


# ---------------------------------------------------------------- 卡片
class TestTactics(Case):
    def setUp(self):
        self.build(make_state(objects=[tank(ALLY_A, (1, 1))]))

    def test_lists_exposed_tactics(self):
        names = [card.name for card in self.commander.tactics()]
        self.assertIn("advance_to_cell", names)
        self.assertNotIn("halt", names)              # 零件不进卡片

    def test_filters_by_query(self):
        names = [card.name for card in self.commander.tactics("推进")]
        self.assertEqual(names, ["advance_covering", "advance_to_cell"])

    def test_query_without_match_returns_empty(self):
        self.assertEqual(self.commander.tactics("没有这种技法"), ())

    def test_conditions_hide_what_cannot_run(self):
        # 视野里没有敌人，接战技法不该出现
        names = [card.name for card in self.commander.tactics()]
        self.assertNotIn("engage_nearest", names)


# ---------------------------------------------------------------- 下达
class TestCall(Case):
    def setUp(self):
        self.build(make_state(objects=[tank(ALLY_A, (1, 1)), tank(ALLY_B, (2, 2))]))

    def test_accepts_and_returns_id_immediately(self):
        results = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),),
            params={"cell": (5, 5)})])
        self.assertTrue(results[0].accepted)
        self.assertTrue(results[0].intent_id)
        self.assertEqual(self.executor.calls, [])     # 受理不等于下发

    def test_unknown_tactic_is_rejected(self):
        results = self.commander.call([CallRequest(tactic="nope", units=(1,))])
        self.assertFalse(results[0].accepted)
        self.assertIn("没有这条技法", results[0].error)

    def test_part_only_tactic_is_rejected(self):
        results = self.commander.call([CallRequest(tactic="halt", units=(1,))])
        self.assertFalse(results[0].accepted)
        self.assertIn("零件", results[0].error)

    def test_bad_parameter_is_rejected(self):
        results = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),),
            params={"cell": (5, 5), "typo": 1})])
        self.assertFalse(results[0].accepted)
        self.assertIn("不认识参数", results[0].error)

    def test_missing_required_parameter_is_rejected(self):
        results = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),))])
        self.assertFalse(results[0].accepted)
        self.assertIn("缺少参数", results[0].error)

    def test_bad_value_is_rejected_up_front(self):
        # 参数只查「在不在」不够：cell 给了 None，要当场说清楚，而不是等技法里炸
        results = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),),
            params={"cell": None})])
        self.assertFalse(results[0].accepted)
        self.assertIn("取值不合法", results[0].error)

    def test_unmet_condition_is_rejected_up_front(self):
        results = self.commander.call([CallRequest(
            tactic="engage_nearest", units=(self.agent(ALLY_A),),
            params={"radius": 8})])
        self.assertFalse(results[0].accepted)
        self.assertIn("此刻用不上", results[0].error)

    def test_foreign_unit_is_rejected(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        self.build(state)
        enemy_agent = self.agent(ENEMY)
        results = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(enemy_agent,),
            params={"cell": (5, 5)})])
        self.assertFalse(results[0].accepted)
        self.assertIn("不是你方", results[0].error)

    def test_empty_units_is_rejected(self):
        results = self.commander.call([CallRequest(tactic="hold_position")])
        self.assertFalse(results[0].accepted)
        self.assertIn("没有给出单位", results[0].error)

    def test_level_gate_applies(self):
        registry = TacticRegistry(TacticPolicy())
        registry.register(Tactic(TacticInfo(name="sneaky", summary="越级",
                                            level=Level.EXPLOIT),
                                 lambda ctx: ()))
        self.build(make_state(objects=[tank(ALLY_A, (1, 1))]), registry=registry)
        results = self.commander.call([CallRequest(
            tactic="sneaky", units=(self.agent(ALLY_A),))])
        self.assertFalse(results[0].accepted)
        self.assertIn("门槛", results[0].error)

    def test_batch_is_independent(self):
        results = self.commander.call([
            CallRequest(tactic="hold_position", units=(self.agent(ALLY_A),)),
            CallRequest(tactic="nope", units=(self.agent(ALLY_B),)),
            CallRequest(tactic="advance_to_cell", units=(self.agent(ALLY_B),),
                        params={"cell": (6, 6)}),
        ])
        self.assertEqual([r.accepted for r in results], [True, False, True])

    def test_unit_already_in_a_task_is_rejected(self):
        first = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),),
            params={"cell": (5, 5)})])
        self.assertTrue(first[0].accepted)
        second = self.commander.call([CallRequest(
            tactic="hold_position", units=(self.agent(ALLY_A),))])
        self.assertFalse(second[0].accepted)
        self.assertIn("已在其它任务里", second[0].error)

    def test_unit_is_free_again_after_settling(self):
        self.commander.call([CallRequest(tactic="hold_position",
                                         units=(self.agent(ALLY_A),))])
        self.tick(self.state)                        # 驻守一拍即结算
        again = self.commander.call([CallRequest(tactic="hold_position",
                                                 units=(self.agent(ALLY_A),))])
        self.assertTrue(again[0].accepted)

    def test_ttl_is_carried(self):
        self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),),
            params={"cell": (5, 5)}, ttl_frames=120)])
        self.assertEqual(self.layer.squads()[0].intent.ttl_frames, 120)

    def test_renders_one_line(self):
        results = self.commander.call([CallRequest(
            tactic="hold_position", units=(self.agent(ALLY_A),))])
        text = results[0].render()
        self.assertNotIn("\n", text)
        self.assertIn("已受理 hold_position#", text)


# ---------------------------------------------------------------- 局势
class TestStatus(Case):
    def setUp(self):
        self.build(make_state(objects=[tank(ALLY_A, (1, 1))]))

    def test_reports_running_task(self):
        self.commander.call([CallRequest(tactic="advance_to_cell",
                                         units=(self.agent(ALLY_A),),
                                         params={"cell": (5, 5)})])
        report = self.commander.status()
        self.assertEqual(len(report.running), 1)
        self.assertEqual(report.running[0]["tactic"], "advance_to_cell")
        self.assertIn("在管 1 项", report.render())

    def test_lists_units_with_position(self):
        # 没有位置，模型无从指定落点
        report = self.commander.status()
        self.assertEqual(len(report.units), 1)
        unit = report.units[0]
        self.assertEqual(unit["cell"], (1, 1))
        self.assertEqual(unit["tactic"], "")
        self.assertIn("格 (1,1)", report.render())
        self.assertIn("可见敌方：无", report.render())

    def test_marks_units_already_in_a_task(self):
        self.commander.call([CallRequest(tactic="advance_to_cell",
                                         units=(self.agent(ALLY_A),),
                                         params={"cell": (5, 5)})])
        unit = self.commander.status().units[0]
        self.assertEqual(unit["tactic"], "advance_to_cell")

    def test_lists_visible_enemies(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (4, 4), house=ENEMY_HOUSE)])
        self.build(state, observation=Observation(
            frame=state.frame, house=state.player_house(),
            own=tuple(o for o in state.objects if o.house == PLAYER_HOUSE),
            visible_enemies=(state.object(ENEMY),), neutral=(), state=state,
            map_data=MAP))
        report = self.commander.status()
        self.assertEqual(len(report.enemies), 1)
        self.assertIn("可见敌方 1", report.render())

    def test_events_are_reported_once(self):
        self.commander.call([CallRequest(tactic="hold_position",
                                         units=(self.agent(ALLY_A),))])
        self.tick(self.state)                       # 驻守一拍即到位并结算
        first = self.commander.status()
        self.assertEqual(len(first.results), 1)
        self.assertEqual(first.results[0]["state"], "satisfied")
        second = self.commander.status()
        self.assertEqual(second.results, ())

    def test_render_is_compact_and_stable(self):
        report = self.commander.status()
        text = report.render()
        self.assertIn("局势｜", text)
        self.assertIn("在管 0 项", text)
        self.assertLess(len(text), 400)

    def test_notices_are_reported(self):
        self.layer._notify("paused", 100, "advance_to_cell", "帧不推进")
        report = self.commander.status()
        self.assertEqual(len(report.notices), 1)
        self.assertIn("paused", report.render())


# ---------------------------------------------------------------- 撤销
class TestCancel(Case):
    def setUp(self):
        self.build(make_state(objects=[tank(ALLY_A, (1, 1))]))

    def test_cancel_stops_the_task(self):
        results = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(self.agent(ALLY_A),),
            params={"cell": (5, 5)})])
        intent_id = results[0].intent_id
        cancelled = self.commander.cancel([intent_id])
        self.assertTrue(cancelled[0]["cancelled"])
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(self.layer.completed[-1]["state"], "superseded")
        self.assertEqual(self.tick(self.state), [])   # 撤销后不再下令

    def test_cancel_unknown_id(self):
        cancelled = self.commander.cancel(["不存在"])
        self.assertFalse(cancelled[0]["cancelled"])
        self.assertIn("没有这条在管任务", Commander.render_cancels(cancelled))


# ---------------------------------------------------------------- 一轮
class TestFakeModelRound(Case):
    """假模型跑一轮：看局势 → 看卡片 → 下达 → 走几拍 → 看结果。"""

    def test_round_trip(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        agent = self.agent(ALLY_A)

        self.assertIn("在管 0 项", self.commander.status().render())
        names = [c.name for c in self.commander.tactics()]
        self.assertIn("advance_to_cell", names)

        result = self.commander.call([CallRequest(
            tactic="advance_to_cell", units=(agent,), params={"cell": (5, 5)})])[0]
        self.assertTrue(result.accepted)

        self.tick(state)                                   # 下令
        self.assertEqual([i.kind for i in self.executor.calls], ["move_to"])
        squad = self.layer.squads()[0]
        goal = squad.units[0].goal

        arrived = make_state(frame=130, objects=[tank(ALLY_A, goal)])
        self.tick(arrived)                                 # 到位并结算

        report = self.commander.status(self.observer.observation)
        self.assertEqual(report.running, ())
        self.assertEqual(len(report.results), 1)
        self.assertEqual(report.results[0]["state"], "satisfied")
        self.assertIn("新结果 1 条", report.render())


class TestUnitPool(Case):
    def test_pool_covers_own_units_only(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        self.build(state)
        pool = UnitPool(self.observation, self.observer.identity)
        self.assertEqual(pool.agents(), (self.agent(ALLY_A),))
        self.assertIsNone(pool.object_of(self.agent(ENEMY)))
        self.assertEqual(pool.cell_of(self.agent(ALLY_A)), (1, 1))


if __name__ == "__main__":
    unittest.main()


class TestMatchBrief(Case):
    """本局信息：首次给详细简报，之后每拍只带一行。"""

    def _state(self, houses, frame=1234):
        return GameState.parse(build_game_state(houses=houses, frame=frame))

    def _both_sides(self):
        return (build_house(PLAYER_HOUSE, current_player=True, faction="Americans"),
                build_house(ENEMY_HOUSE, faction="Russians"))

    def test_first_status_carries_the_brief(self):
        self.build(self._state(self._both_sides()))
        text = self.commander.status(self.observation).render()
        self.assertIn("本局｜", text)
        self.assertIn("地图", text)
        self.assertIn("水域", text)
        self.assertIn("参战 2 方", text)
        self.assertIn("科技等级", text)

    def test_brief_is_reported_only_once(self):
        self.build(self._state(self._both_sides()))
        self.commander.status(self.observation)
        later = self.commander.status(self.observation).render()
        # 一行还在（模型每拍都该看到自己在什么局里），详细的没了
        self.assertIn("本局｜", later)
        self.assertNotIn("科技等级", later)

    def test_neutral_house_is_not_a_combatant(self):
        self.build(self._state(self._both_sides()
                               + (build_house(0x3000, faction="Neutral"),)))
        self.assertIn("参战 2 方", self.commander.status(self.observation).render())

    def test_defeated_house_is_marked(self):
        self.build(self._state((build_house(PLAYER_HOUSE, current_player=True),
                                build_house(ENEMY_HOUSE, defeated=True))))
        self.assertIn("已出局", self.commander.status(self.observation).render())

    def test_no_combatants_means_no_brief(self):
        # 一个参战方都数不出来时，不报一份空的
        self.build(self._state((build_house(PLAYER_HOUSE, current_player=True,
                                            faction="Neutral"),)))
        text = self.commander.status(self.observation).render()
        self.assertNotIn("本局｜", text)
        self.assertFalse(self.commander._briefed)


class TestStatusEvents(Case):
    """游戏事件走 `status` 的「读走即清空」——与任务结果同一套语义。"""

    def _event(self):
        from ra2agent.events import Event, EventKind, Subject
        return Event(kind=EventKind.LOW_POWER, frame=self.state.frame,
                     subject=Subject("house", 0, "me"),
                     data={"drain": 150, "output": 100})

    def test_reported_once(self):
        self.build(GameState.parse(build_game_state(houses=[
            build_house(PLAYER_HOUSE, current_player=True)])))
        self.observer.events.record([self._event()])
        first = self.commander.status(self.observation)
        self.assertEqual(len(first.events), 1)
        self.assertIn("新事件 1 条", first.render())
        self.assertIn("电力不足", first.render())
        self.assertEqual(self.commander.status(self.observation).events, ())

    def test_no_events_means_no_section(self):
        self.build(GameState.parse(build_game_state(houses=[
            build_house(PLAYER_HOUSE, current_player=True)])))
        self.assertNotIn("新事件", self.commander.status(self.observation).render())

    def test_task_results_keep_their_own_section(self):
        # 游戏事件与任务结果是两回事，各有各的段落
        self.build(GameState.parse(build_game_state(houses=[
            build_house(PLAYER_HOUSE, current_player=True)])))
        self.observer.events.record([self._event()])
        text = self.commander.status(self.observation).render()
        self.assertIn("新事件 1 条", text)
        self.assertNotIn("新结果", text)


class TestDescribeMap(unittest.TestCase):
    def test_water_ratio(self):
        from ra2agent.command import describe_map
        m = MapData(width=10, height=10, columns={"land_type": [LandType.WATER] * 25
                                                  + [LandType.CLEAR] * 75})
        self.assertEqual(describe_map(m), "地图 10×10，水域 25%")

    def test_no_map_yet(self):
        from ra2agent.command import describe_map
        self.assertEqual(describe_map(None), "")

    def test_land_only_is_zero_percent(self):
        from ra2agent.command import describe_map
        m = MapData(width=2, height=2, columns={"land_type": [LandType.CLEAR] * 4})
        self.assertEqual(describe_map(m), "地图 2×2，水域 0%")
