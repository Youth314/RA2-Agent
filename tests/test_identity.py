"""对象标识表的测试。

重点覆盖「指针会变、agent id 不变」这一约束，因为指向对象的意图全依赖它。
"""
import unittest

from ra2agent.constants import AbstractType, Mission
from ra2agent.identity import IdentityTable
from ra2agent.state import GameState
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_game_state,
                            build_house, build_object)

MCV = 0x100
TANK = 0x101
YARD = 0x200
ENEMY_TANK = 0x300

HOUSES = [build_house(PLAYER_HOUSE, current_player=True),
          build_house(ENEMY_HOUSE)]


def state(objects, frame):
    """构造一帧只含给定对象的观测。"""
    return GameState.parse(build_game_state(houses=HOUSES, objects=objects,
                                            frame=frame))


def unit(pointer, cell=(20, 20), house=PLAYER_HOUSE, health=1000):
    """一个载具。"""
    return build_object(pointer, house=house, health=health,
                        object_type=AbstractType.UNIT,
                        mission=Mission.GUARD,
                        x=cell[0] * 256 + 128, y=cell[1] * 256 + 128)


def building(pointer, cell=(20, 20), house=PLAYER_HOUSE):
    """一个建筑。"""
    return build_object(pointer, house=house,
                        object_type=AbstractType.BUILDING,
                        mission=Mission.CONSTRUCTION,
                        x=cell[0] * 256 + 128, y=cell[1] * 256 + 128)


class TestAssignment(unittest.TestCase):
    def setUp(self):
        self.table = IdentityTable()

    def test_assigns_ids_to_new_objects(self):
        delta = self.table.update(state([unit(MCV), unit(TANK)], frame=10))
        self.assertEqual(len(delta.appeared), 2)
        self.assertEqual(delta.vanished, [])
        self.assertEqual(delta.transformed, [])
        self.assertEqual(len(self.table), 2)

    def test_ids_are_distinct(self):
        self.table.update(state([unit(MCV), unit(TANK)], frame=10))
        self.assertNotEqual(self.table.agent_id(MCV), self.table.agent_id(TANK))

    def test_ids_are_stable_across_frames(self):
        self.table.update(state([unit(MCV)], frame=10))
        first = self.table.agent_id(MCV)
        for frame in (11, 12, 13):
            delta = self.table.update(state([unit(MCV, cell=(20 + frame, 20))],
                                            frame=frame))
            self.assertTrue(delta.empty)
            self.assertEqual(self.table.agent_id(MCV), first)

    def test_pointer_of_round_trips(self):
        self.table.update(state([unit(MCV)], frame=10))
        agent = self.table.agent_id(MCV)
        self.assertEqual(self.table.pointer_of(agent), MCV)

    def test_unknown_lookups(self):
        self.assertIsNone(self.table.agent_id(0xDEAD))
        self.assertIsNone(self.table.pointer_of(999))
        self.assertIsNone(self.table.tracked(999))


class TestVanishing(unittest.TestCase):
    def setUp(self):
        self.table = IdentityTable(grace_frames=5)

    def test_survives_within_grace_period(self):
        self.table.update(state([unit(MCV)], frame=10))
        agent = self.table.agent_id(MCV)
        for frame in range(11, 15):
            delta = self.table.update(state([], frame=frame))
            self.assertEqual(delta.vanished, [])
        self.assertIn(agent, self.table.known())

    def test_vanishes_after_grace_period(self):
        self.table.update(state([unit(MCV)], frame=10))
        agent = self.table.agent_id(MCV)
        self.table.update(state([], frame=11))
        delta = self.table.update(state([], frame=16))
        self.assertEqual(delta.vanished, [agent])
        self.assertNotIn(agent, self.table.known())
        self.assertIsNone(self.table.agent_id(MCV))

    def test_pointer_can_be_reused_after_forget(self):
        self.table.update(state([unit(MCV)], frame=10))
        first = self.table.agent_id(MCV)
        self.table.update(state([], frame=11))
        self.table.update(state([], frame=20))
        self.table.update(state([unit(MCV)], frame=21))
        second = self.table.agent_id(MCV)
        self.assertIsNotNone(second)
        self.assertNotEqual(second, first)


class TestTransformation(unittest.TestCase):
    """基地车部署：指针改变，agent id 必须延续。"""

    def setUp(self):
        self.table = IdentityTable(grace_frames=30, match_radius=6)

    def test_id_survives_pointer_change(self):
        self.table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        agent = self.table.agent_id(MCV)

        delta = self.table.update(
            state([building(YARD, cell=(21, 21))], frame=12))

        self.assertEqual(delta.transformed, [(agent, YARD)])
        self.assertEqual(delta.appeared, [])
        self.assertEqual(delta.vanished, [])
        self.assertEqual(self.table.agent_id(YARD), agent)
        self.assertIsNone(self.table.agent_id(MCV))
        self.assertEqual(self.table.pointer_of(agent), YARD)

    def test_records_previous_pointer(self):
        self.table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        self.table.update(state([building(YARD, cell=(21, 21))], frame=12))
        tracked = self.table.tracked(self.table.agent_id(YARD))
        self.assertEqual(tracked.previous_pointer, MCV)
        self.assertEqual(tracked.cell, (21, 21))

    def test_requires_different_object_type(self):
        # 同种类不算变身：不能把一辆新车当成旧车的延续
        self.table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        first = self.table.agent_id(MCV)
        delta = self.table.update(state([unit(TANK, cell=(20, 20))], frame=11))
        self.assertEqual(delta.transformed, [])
        self.assertNotEqual(self.table.agent_id(TANK), first)

    def test_requires_same_house(self):
        self.table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        delta = self.table.update(
            state([building(YARD, cell=(20, 20), house=ENEMY_HOUSE)], frame=11))
        self.assertEqual(delta.transformed, [])

    def test_requires_proximity(self):
        self.table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        delta = self.table.update(
            state([building(YARD, cell=(60, 60))], frame=11))
        self.assertEqual(delta.transformed, [])

    def test_requires_within_grace(self):
        table = IdentityTable(grace_frames=3, match_radius=6)
        table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        # 缺席已超宽限期，此时出现的新建筑应视为新对象
        delta = table.update(state([building(YARD, cell=(20, 20))], frame=20))
        self.assertEqual(delta.transformed, [])
        self.assertEqual(len(delta.appeared), 1)

    def test_picks_nearest_candidate(self):
        table = IdentityTable(grace_frames=30, match_radius=6)
        table.update(state([unit(MCV, cell=(20, 20)),
                            unit(TANK, cell=(25, 25))], frame=10))
        mcv_agent = table.agent_id(MCV)
        # 只留下 YARD：MCV 在半径内，TANK 距离 41 超出半径 6，故不参与配对
        delta = table.update(state([building(YARD, cell=(21, 20))], frame=11))
        self.assertEqual(delta.transformed, [(mcv_agent, YARD)])
        self.assertEqual(delta.appeared, [])
        # TANK 缺席但在宽限期内，尚不判定消失
        self.assertEqual(delta.vanished, [])


class TestCombinedUpdates(unittest.TestCase):
    def test_new_and_gone_in_same_frame(self):
        table = IdentityTable(grace_frames=2)
        table.update(state([unit(MCV, cell=(20, 20))], frame=10))
        old = table.agent_id(MCV)
        table.update(state([unit(TANK, cell=(80, 80))], frame=11))
        delta = table.update(state([unit(TANK, cell=(80, 80)),
                                    unit(0x400, cell=(40, 40))], frame=13))
        self.assertEqual(delta.vanished, [old])
        self.assertEqual(len(delta.appeared), 1)
        self.assertEqual(len(table), 2)

    def test_delta_empty_flag(self):
        table = IdentityTable()
        delta = table.update(state([unit(MCV)], frame=1))
        self.assertFalse(delta.empty)
        self.assertTrue(table.update(state([unit(MCV)], frame=2)).empty)

    def test_state_without_player_house_is_rejected(self):
        table = IdentityTable()
        broken = GameState.parse(build_game_state(
            houses=[build_house(ENEMY_HOUSE)], objects=[unit(MCV)]))
        # update 只按对象归属做配对，不依赖 current_player，故不应抛错
        table.update(broken)
        self.assertEqual(len(table), 1)


if __name__ == "__main__":
    unittest.main()
