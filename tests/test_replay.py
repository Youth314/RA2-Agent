"""回放验证的测试。

场景用测试夹具现搭，不依赖任何录制文件；回放过程不连接游戏。
"""
import json
import os
import tempfile
import unittest

from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.formation import blocked_cells
from ra2agent.intents import Stance
from ra2agent.replay import (Expectation, ReplayReport, Scenario, _parse_params,
                             replay)
from ra2agent.state import GameState, MapData
from ra2agent.tactics import Tactic, TacticInfo, TacticPolicy, TacticRegistry
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_game_state,
                            build_house, build_map_soa, build_object)

SIDE = 12
TANK = 0xA1
ENEMY = 0xB1


def make_map(shrouded=None):
    cells = SIDE * SIDE
    return MapData.parse(build_map_soa(
        width=SIDE, height=SIDE,
        shrouded=shrouded if shrouded is not None else [0] * cells,
        land=[LandType.CLEAR] * cells))


MAP = make_map()


def at(cell):
    return cell[0] * 256 + 128, cell[1] * 256 + 128


def tank(pointer, cell, house=PLAYER_HOUSE, **kwargs):
    x, y = at(cell)
    return build_object(pointer, house=house, object_type=AbstractType.UNIT,
                        mission=Mission.GUARD, x=x, y=y, **kwargs)


def frame(frame_number, cell, pointer=TANK):
    """一帧只有一辆车，位置给定。"""
    return build_game_state(
        frame=frame_number,
        houses=[build_house(PLAYER_HOUSE, current_player=True),
                build_house(ENEMY_HOUSE)],
        objects=[tank(pointer, cell)])


def scenario_of(cells, start_frame=100):
    """按给定的位置序列造一个场景。"""
    return Scenario(frames=tuple(frame(start_frame + i, cell)
                                 for i, cell in enumerate(cells)),
                    map_soa=MAP.raw, note="测试")


def agent_of(scenario, pointer=TANK):
    """场景第一帧里某对象的 agent id。"""
    identity_states = scenario.states()
    from ra2agent.identity import IdentityTable
    table = IdentityTable()
    table.update(identity_states[0])
    return table.agent_id(pointer)


# ---------------------------------------------------------------- 录制
class TestScenario(unittest.TestCase):
    def test_round_trip_through_json(self):
        scenario = scenario_of([(1, 1), (2, 1), (3, 1)], start_frame=50)
        restored = Scenario.from_dict(json.loads(json.dumps(scenario.to_dict())))
        self.assertEqual(len(restored.frames), 3)
        self.assertEqual(restored.states()[0].frame, 50)
        self.assertEqual(restored.map_data().width, SIDE)

    def test_save_and_load(self):
        scenario = scenario_of([(1, 1), (2, 1)])
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "s.json")
            scenario.save(path)
            loaded = Scenario.load(path)
        self.assertEqual(loaded.states()[1].object(TANK).coordinates.cell, (2, 1))

    def test_version_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            Scenario.from_dict({"version": 99, "frames": []})

    def test_empty_scenario_has_no_map(self):
        scenario = Scenario(frames=(frame(1, (1, 1)),))
        self.assertIsNone(scenario.map_data())


# ---------------------------------------------------------------- 回放
class TestReplay(unittest.TestCase):
    def setUp(self):
        # 车从 (1,1) 一路走到 (5,1)
        self.scenario = scenario_of([(1, 1), (2, 1), (3, 1), (4, 1), (5, 1), (5, 1)])
        self.agent = agent_of(self.scenario)

    def test_advance_issues_one_order_per_unit(self):
        report = replay(self.scenario, "advance_to_cell", (self.agent,),
                        {"cell": (5, 1)}, ticks=3)
        self.assertEqual(report.intents[0][1], ("move_to",))
        self.assertIn("前置校验：全部通过", report.render())

    def test_arrival_settles_satisfied(self):
        report = replay(self.scenario, "advance_to_cell", (self.agent,),
                        {"cell": (5, 1)}, ticks=8,
                        expect=Expectation(settle="satisfied"))
        self.assertTrue(report.ok, report.failures)
        self.assertEqual(report.settlement["state"], "satisfied")
        self.assertEqual(report.settlement["arrived"], [self.agent])

    def test_hold_settles_at_once(self):
        report = replay(self.scenario, "hold_position", (self.agent,), {},
                        ticks=3, expect=Expectation(settle="satisfied"))
        self.assertTrue(report.ok, report.failures)
        self.assertEqual(report.intents[0][1], ("hold",))

    def test_enemy_tactic_is_denied_without_enemies(self):
        # 场景里没有可见敌人：条件不满足，一点动静都不该有
        report = replay(self.scenario, "engage_nearest", (self.agent,),
                        {"radius": 8}, ticks=3)
        self.assertEqual(report.plan_errors, ())
        self.assertIn("只产出 0 条意图", "；".join(report.failures))

    def test_out_of_map_cell_is_caught_by_precheck(self):
        # 越界坐标真机会崩；回放要在发出去之前抓住
        report = replay(self.scenario, "advance_to_cell", (self.agent,),
                        {"cell": (999, 999)}, ticks=3)
        self.assertTrue(report.plan_errors)
        self.assertIn("InvalidCommand", report.plan_errors[0])
        self.assertFalse(report.ok)

    def test_unknown_unit_gives_a_verdict_not_a_crash(self):
        report = replay(self.scenario, "advance_to_cell", (999999,),
                        {"cell": (5, 1)}, ticks=3)
        self.assertFalse(report.ok)
        self.assertIn("没有可用对象", "；".join(report.failures))

    def test_unknown_tactic_gives_a_verdict(self):
        report = replay(self.scenario, "no_such_tactic", (self.agent,), {}, ticks=2)
        self.assertFalse(report.ok)
        self.assertIn("no_such_tactic", "；".join(report.failures))

    def test_report_render_is_stable(self):
        report = replay(self.scenario, "advance_to_cell", (self.agent,),
                        {"cell": (5, 1)}, ticks=3)
        text = report.render()
        self.assertIn("回放 advance_to_cell", text)
        self.assertIn("判定：", text)
        for line in text.splitlines():
            self.assertFalse(line.startswith(" "))

    def test_expectation_failure_is_reported(self):
        report = replay(self.scenario, "advance_to_cell", (self.agent,),
                        {"cell": (5, 1)}, ticks=1, expect=Expectation(settle="satisfied"))
        self.assertFalse(report.ok)
        self.assertIn("未结束", "；".join(report.failures))

    def test_custom_registry_can_be_used(self):
        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="noop", summary="什么都不做"),
                                 lambda ctx: ()))
        report = replay(self.scenario, "noop", (self.agent,), {}, ticks=2,
                        registry=registry, expect=Expectation(min_intents=0))
        self.assertTrue(report.ok, report.failures)

    def test_empty_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            replay(Scenario(frames=()), "hold_position", (), {}, ticks=1)


class TestParams(unittest.TestCase):
    def test_parses_json_values(self):
        self.assertEqual(_parse_params(["cell=5,6", "radius=8", "stance=passive"]),
                         {"cell": (5, 6), "radius": 8, "stance": "passive"})
        self.assertEqual(_parse_params(["cell=[5,6]"]), {"cell": [5, 6]})

    def test_bare_string_stays(self):
        self.assertEqual(_parse_params(["name=abc"]), {"name": "abc"})

    def test_missing_equals_is_rejected(self):
        with self.assertRaises(ValueError):
            _parse_params(["cell"])


if __name__ == "__main__":
    unittest.main()
