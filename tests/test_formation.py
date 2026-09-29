"""队形展开的测试。

纯计算，重点是把不可站立的格排除干净，并保证同样输入得到同样结果。
"""
import unittest

from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.formation import blocked_cells, formation_cells
from ra2agent.state import GameState, MapData
from tests.fixtures import (PLAYER_HOUSE, build_game_state, build_house,
                            build_map_soa, build_object)

SIDE = 9
CENTER = (4, 4)


def make_map(shrouded=None, land=None):
    cells = SIDE * SIDE
    return MapData.parse(build_map_soa(
        width=SIDE, height=SIDE,
        shrouded=shrouded if shrouded is not None else [0] * cells,
        land=land if land is not None else [LandType.CLEAR] * cells))


def make_state(objects=()):
    return GameState.parse(build_game_state(
        houses=[build_house(PLAYER_HOUSE, current_player=True)],
        objects=list(objects)))


class TestFormationCells(unittest.TestCase):
    def setUp(self):
        self.map = make_map()

    def test_center_comes_first(self):
        cells = formation_cells(CENTER, 5, self.map)
        self.assertEqual(cells[0], CENTER)
        self.assertEqual(len(cells), 5)

    def test_sorted_by_distance(self):
        cells = formation_cells(CENTER, 9, self.map)
        distances = [max(abs(x - CENTER[0]), abs(y - CENTER[1])) for x, y in cells]
        self.assertEqual(distances, sorted(distances))

    def test_deterministic(self):
        self.assertEqual(formation_cells(CENTER, 6, self.map),
                         formation_cells(CENTER, 6, self.map))

    def test_skips_blocked_cells(self):
        cells = formation_cells(CENTER, 4, self.map, blocked={CENTER, (5, 4)})
        self.assertNotIn(CENTER, cells)
        self.assertNotIn((5, 4), cells)

    def test_skips_shrouded_cells(self):
        shrouded = [0] * (SIDE * SIDE)
        shrouded[4 * SIDE + 4] = 1                     # (4,4) 未探索
        cells = formation_cells(CENTER, 3, make_map(shrouded=shrouded))
        self.assertNotIn(CENTER, cells)

    def test_skips_impassable_land(self):
        land = [LandType.CLEAR] * (SIDE * SIDE)
        land[4 * SIDE + 4] = LandType.WATER
        cells = formation_cells(CENTER, 3, make_map(land=land))
        self.assertNotIn(CENTER, cells)

    def test_respects_bounds(self):
        cells = formation_cells((0, 0), 20, self.map)
        for x, y in cells:
            self.assertTrue(0 <= x < SIDE and 0 <= y < SIDE)

    def test_returns_what_exists(self):
        cells = formation_cells((0, 0), 500, self.map, radius=1)
        self.assertEqual(len(cells), 4)                # 半径为 1 只有 3×3 减越界

    def test_zero_or_negative_count(self):
        self.assertEqual(formation_cells(CENTER, 0, self.map), ())
        self.assertEqual(formation_cells(CENTER, -3, self.map), ())

    def test_map_is_required(self):
        with self.assertRaises(ValueError):
            formation_cells(CENTER, 2, None)


class TestBlockedCells(unittest.TestCase):
    def test_buildings_block(self):
        state = make_state([
            build_object(0xA1, object_type=AbstractType.BUILDING, x=4 * 256 + 128,
                         y=4 * 256 + 128, mission=Mission.GUARD),
            build_object(0xA2, object_type=AbstractType.UNIT, x=5 * 256 + 128,
                         y=4 * 256 + 128),
        ])
        self.assertEqual(blocked_cells(state), frozenset({(4, 4)}))

    def test_limbo_buildings_do_not_block(self):
        state = make_state([
            build_object(0xA1, object_type=AbstractType.BUILDING, in_limbo=True,
                         x=4 * 256 + 128, y=4 * 256 + 128)])
        self.assertEqual(blocked_cells(state), frozenset())


if __name__ == "__main__":
    unittest.main()
