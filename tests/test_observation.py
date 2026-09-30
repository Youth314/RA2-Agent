"""观测层与迷雾过滤的测试。"""
import unittest

from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.engine.observation import Observation, Observer
from ra2agent.engine.state import GameState, MapData, TypeTable
from tests.fixtures import (ENEMY_HOUSE, NEUTRAL_HOUSE, PLAYER_HOUSE,
                            build_cell, build_game_state, build_house,
                            build_map_soa, build_object, build_type_table)

ALLY_TANK = 0xA1
ENEMY_TANK = 0xB1
ENEMY_IN_BUILDING = 0xB2
NEUTRAL_CIVILIAN = 0xC1
LIMBO_OBJECT = 0xA9

SIDE = 4


def make_map(shrouded_rows):
    """按行给出遮蔽标志构造地图。"""
    flat = [bit for row in shrouded_rows for bit in row]
    return MapData.parse(build_map_soa(
        width=SIDE, height=SIDE, shrouded=flat,
        land=[LandType.CLEAR] * (SIDE * SIDE)))


def make_state(frame=100, objects=()):
    return GameState.parse(build_game_state(
        frame=frame,
        houses=[build_house(PLAYER_HOUSE, current_player=True),
                build_house(ENEMY_HOUSE),
                build_house(NEUTRAL_HOUSE, faction="Neutral")],
        objects=list(objects)))


def at(cell):
    return cell[0] * 256 + 128, cell[1] * 256 + 128


def tank(pointer, cell, house=PLAYER_HOUSE, in_limbo=False):
    x, y = at(cell)
    return build_object(pointer, house=house, object_type=AbstractType.UNIT,
                        mission=Mission.GUARD, x=x, y=y, in_limbo=in_limbo)


def civilian(pointer, cell):
    x, y = at(cell)
    return build_object(pointer, house=NEUTRAL_HOUSE,
                        object_type=AbstractType.BUILDING,
                        mission=Mission.GUARD, x=x, y=y)


class FakeClient:
    """按脚本返回状态的最小客户端。"""

    def __init__(self, states=(), map_data=None, types=None):
        self._states = list(states)
        self._map = map_data
        self._types = types
        self.map_calls = 0
        self.type_calls = 0

    def get_state(self):
        return self._states.pop(0)

    def read_map(self):
        self.map_calls += 1
        return self._map

    def read_object_types(self):
        self.type_calls += 1
        return self._types


class TestFogFiltering(unittest.TestCase):
    """迷雾过滤：Agent 只能看到己方可见的世界。"""

    def setUp(self):
        # 仅 (0,0) 与 (1,0) 已探索
        self.map = make_map([[0, 0, 1, 1],
                             [1, 1, 1, 1],
                             [1, 1, 1, 1],
                             [1, 1, 1, 1]])
        self.state = make_state(objects=[
            tank(ALLY_TANK, (0, 0)),
            tank(ENEMY_TANK, (1, 0), house=ENEMY_HOUSE),          # 已探索，可见
            tank(ENEMY_IN_BUILDING, (3, 3), house=ENEMY_HOUSE),   # 未探索，不可见
            civilian(NEUTRAL_CIVILIAN, (1, 0)),
            tank(LIMBO_OBJECT, (0, 0), in_limbo=True),
        ])
        self.observer = Observer(FakeClient(map_data=self.map),
                                 map_data=self.map)
        self.observer.absorb(self.state)
        self.observation = self.observer.observe()

    def test_own_always_visible(self):
        self.assertIn(ALLY_TANK, {o.pointer for o in self.observation.own})

    def test_limbo_is_excluded(self):
        self.assertNotIn(LIMBO_OBJECT, {o.pointer for o in self.observation.own})
        self.assertNotIn(LIMBO_OBJECT,
                         {o.pointer for o in self.observation.visible_enemies})

    def test_visible_enemy_included(self):
        self.assertEqual({o.pointer for o in self.observation.visible_enemies},
                         {ENEMY_TANK})

    def test_unseen_enemy_excluded(self):
        all_pointers = ({o.pointer for o in self.observation.own}
                        | {o.pointer for o in self.observation.visible_enemies}
                        | {o.pointer for o in self.observation.neutral})
        self.assertNotIn(ENEMY_IN_BUILDING, all_pointers)

    def test_neutral_is_separated_from_enemies(self):
        self.assertEqual({o.pointer for o in self.observation.neutral},
                         {NEUTRAL_CIVILIAN})
        self.assertNotIn(NEUTRAL_CIVILIAN,
                         {o.pointer for o in self.observation.visible_enemies})

    def test_no_map_means_nothing_visible(self):
        observer = Observer(FakeClient(), map_data=None)
        observer.absorb(self.state)
        observation = observer.observe()
        self.assertEqual(observation.visible_enemies, ())
        self.assertEqual(observation.neutral, ())

    def test_exploring_reveals_enemy(self):
        # 迷雾是永久已探索标志：一旦探明，敌方对象随之出现
        # (3,3) 的行主序下标为 15，故只把最后一格置为已探索
        revealed = make_map([[0, 0, 1, 1],
                             [1, 1, 1, 1],
                             [1, 1, 1, 1],
                             [1, 1, 1, 0]])
        observer = Observer(FakeClient(), map_data=revealed)
        observer.absorb(self.state)
        self.assertIn(ENEMY_IN_BUILDING,
                      {o.pointer for o in observer.observe().visible_enemies})


class TestIncrementalMap(unittest.TestCase):
    def setUp(self):
        self.map = make_map([[1] * SIDE] * SIDE)
        self.observer = Observer(FakeClient(), map_data=self.map,
                                 types=TypeTable())

    def test_cells_difference_is_applied(self):
        state = GameState.parse(build_game_state(
            frame=10,
            houses=[build_house(PLAYER_HOUSE, current_player=True)],
            cells=[build_cell(0, shrouded=False)]))
        self.assertEqual(self.observer.absorb(state), 1)
        self.assertFalse(self.map.shrouded(0, 0))

    def test_out_of_range_difference_is_ignored(self):
        state = GameState.parse(build_game_state(
            frame=10,
            houses=[build_house(PLAYER_HOUSE, current_player=True)],
            cells=[build_cell(999, shrouded=False)]))
        self.assertEqual(self.observer.absorb(state), 0)

    def test_explored_ratio(self):
        self.assertEqual(self.observer.explored_ratio(), 0.0)
        state = GameState.parse(build_game_state(
            frame=10,
            houses=[build_house(PLAYER_HOUSE, current_player=True)],
            cells=[build_cell(i, shrouded=False) for i in range(4)]))
        self.observer.absorb(state)
        self.assertEqual(self.observer.explored_ratio(), 4 / 16)


class TestBootstrap(unittest.TestCase):
    def test_fetches_map_and_types_once(self):
        client = FakeClient(map_data=make_map([[0] * SIDE] * SIDE),
                            types=TypeTable())
        observer = Observer(client).bootstrap()
        self.assertEqual(client.map_calls, 1)
        self.assertEqual(client.type_calls, 1)
        observer.bootstrap()
        self.assertEqual(client.map_calls, 1)
        self.assertEqual(client.type_calls, 1)

    def test_poll_advances_identity(self):
        client = FakeClient(states=[make_state(frame=1, objects=[tank(ALLY_TANK, (0, 0))]),
                                    make_state(frame=2, objects=[tank(ALLY_TANK, (0, 0))])],
                            map_data=make_map([[0] * SIDE] * SIDE),
                            types=TypeTable())
        observer = Observer(client).bootstrap()
        first = observer.poll()
        self.assertEqual(len(observer.identity), 1)
        agent_id = observer.identity.agent_id(ALLY_TANK)
        second = observer.poll()
        self.assertEqual(observer.identity.agent_id(ALLY_TANK), agent_id)
        self.assertEqual(first.frame, 1)
        self.assertEqual(second.frame, 2)


class TestObservationViews(unittest.TestCase):
    def setUp(self):
        self.map = make_map([[0] * SIDE] * SIDE)
        state = make_state(objects=[
            tank(ALLY_TANK, (0, 0)),
            build_object(0xA2, house=PLAYER_HOUSE,
                         object_type=AbstractType.BUILDING,
                         mission=Mission.GUARD, x=128, y=128),
            build_object(0xA3, house=PLAYER_HOUSE,
                         object_type=AbstractType.INFANTRY,
                         mission=Mission.GUARD, x=128, y=128),
        ])
        observer = Observer(FakeClient(), map_data=self.map)
        observer.absorb(state)
        self.observation = observer.observe()

    def test_views_split_by_kind(self):
        self.assertEqual([o.pointer for o in self.observation.units], [ALLY_TANK])
        self.assertEqual(len(self.observation.buildings), 1)
        self.assertEqual(len(self.observation.infantry), 1)

    def test_summary_is_a_single_line(self):
        text = self.observation.summary()
        self.assertIn("帧 100", text)
        self.assertIn("己方 3", text)
        self.assertNotIn("\n", text)


if __name__ == "__main__":
    unittest.main()
