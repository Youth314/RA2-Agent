"""状态解析的测试。

用 `proto` 的编码器手工构造消息，不依赖录制文件，使测试可离线运行。
"""
import unittest

from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.errors import ProtocolError
from ra2agent.state import (Coordinates, GameState, MapData, TypeTable,
                            cell_center, parse_cell, parse_coordinates)
from tests.fixtures import (ENEMY_HOUSE, NEUTRAL_HOUSE, PLAYER_HOUSE,
                            build_cell, build_coordinates, build_factory,
                            build_game_state, build_house, build_map_soa,
                            build_object, build_type_table)


class TestCoordinates(unittest.TestCase):
    def test_parse(self):
        parsed = parse_coordinates(build_coordinates(11, 22, 3))
        self.assertEqual((parsed.x, parsed.y, parsed.z), (11, 22, 3))

    def test_cell_conversion_matches_engine(self):
        self.assertEqual(Coordinates(0, 0).cell, (0, 0))
        self.assertEqual(Coordinates(255, 255).cell, (0, 0))
        self.assertEqual(Coordinates(256, 256).cell, (1, 1))
        self.assertEqual(Coordinates(511, 511).cell, (1, 1))

    def test_negative_truncates_toward_zero(self):
        # C++ 的整数除法向零截断，故 -1/256 = 0，负坐标会落进格 0
        self.assertEqual(Coordinates(-1, 0).cell, (0, 0))
        self.assertEqual(Coordinates(-255, 0).cell, (0, 0))
        self.assertEqual(Coordinates(-256, 0).cell, (-1, 0))

    def test_cell_center_round_trips(self):
        for cell in [(0, 0), (3, 4), (143, 143)]:
            with self.subTest(cell=cell):
                self.assertEqual(cell_center(*cell).cell, cell)


class TestGameState(unittest.TestCase):
    def setUp(self):
        self.payload = build_game_state(
            frame=555,
            houses=[build_house(PLAYER_HOUSE, current_player=True),
                    build_house(ENEMY_HOUSE),
                    build_house(NEUTRAL_HOUSE, faction="Neutral")],
            objects=[build_object(0xA1, mission=Mission.GUARD),
                     build_object(0xA2, mission=Mission.CONSTRUCTION,
                                  object_type=AbstractType.BUILDING),
                     build_object(0xB1, house=ENEMY_HOUSE,
                                  object_type=AbstractType.INFANTRY)],
            factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=54)],
            cells=[build_cell(7, shrouded=True)],
        )
        self.state = GameState.parse(self.payload)

    def test_scalars(self):
        self.assertEqual(self.state.frame, 555)
        self.assertEqual(self.state.stage, 2)
        self.assertEqual(self.state.tech_level, 10)

    def test_objects_parsed(self):
        self.assertEqual(len(self.state.objects), 3)
        first = self.state.object(0xA1)
        self.assertEqual(first.health, 300)
        self.assertEqual(first.coordinates, Coordinates(1000, 2000, 0))
        self.assertEqual(first.mission, Mission.GUARD)
        self.assertEqual(first.object_type, AbstractType.UNIT)
        self.assertTrue(first.is_unit)
        self.assertFalse(first.is_building)

    def test_building_flag(self):
        self.assertTrue(self.state.object(0xA2).is_building)

    def test_require_object_raises(self):
        self.assertIsNone(self.state.object(0xDEAD))
        with self.assertRaises(ProtocolError):
            self.state.require_object(0xDEAD)

    def test_player_house(self):
        self.assertEqual(self.state.player_house().pointer, PLAYER_HOUSE)
        self.assertEqual(self.state.player_house().money, 10000)

    def test_player_house_requires_exactly_one(self):
        none = GameState.parse(build_game_state(
            houses=[build_house(ENEMY_HOUSE)]))
        with self.assertRaises(ProtocolError):
            none.player_house()
        two = GameState.parse(build_game_state(
            houses=[build_house(PLAYER_HOUSE, current_player=True),
                    build_house(ENEMY_HOUSE, current_player=True)]))
        with self.assertRaises(ProtocolError):
            two.player_house()

    def test_own_objects_excludes_enemy(self):
        self.assertEqual({o.pointer for o in self.state.own_objects()},
                         {0xA1, 0xA2})

    def test_enemy_houses_excludes_neutral(self):
        self.assertEqual([h.pointer for h in self.state.enemy_houses()],
                         [ENEMY_HOUSE])

    def test_factories(self):
        self.assertEqual(len(self.state.own_factories()), 1)
        self.assertTrue(self.state.own_factories()[0].completed)

    def test_cells_difference(self):
        self.assertEqual(len(self.state.cells_difference), 1)
        self.assertEqual(self.state.cells_difference[0].index, 7)
        self.assertTrue(self.state.cells_difference[0].shrouded)

    def test_missing_house_is_ignored(self):
        # 无 current_player 时 own_objects 也应报错而非静默返回空
        state = GameState.parse(build_game_state(
            houses=[build_house(ENEMY_HOUSE)],
            objects=[build_object(0xA1)]))
        with self.assertRaises(ProtocolError):
            state.own_objects()


class TestMapData(unittest.TestCase):
    def setUp(self):
        # 2x2：仅 (0,0) 已探索且为 Clear
        self.map = MapData.parse(build_map_soa(
            width=2, height=2,
            shrouded=[0, 1, 1, 1],
            land=[LandType.CLEAR, LandType.WATER,
                  LandType.WATER, LandType.WATER]))

    def test_dimensions(self):
        self.assertEqual((self.map.width, self.map.height), (2, 2))
        self.assertEqual(self.map.cell_count, 4)

    def test_bounds(self):
        self.assertTrue(self.map.in_bounds(1, 1))
        self.assertFalse(self.map.in_bounds(2, 1))
        self.assertFalse(self.map.in_bounds(-1, 0))

    def test_cell_index_row_major(self):
        self.assertEqual(self.map.cell_index(0, 0), 0)
        self.assertEqual(self.map.cell_index(1, 0), 1)
        self.assertEqual(self.map.cell_index(0, 1), 2)

    def test_shrouded_and_land(self):
        self.assertFalse(self.map.shrouded(0, 0))
        self.assertTrue(self.map.shrouded(1, 0))
        self.assertEqual(self.map.land_type(0, 0), LandType.CLEAR)
        self.assertEqual(self.map.land_type(1, 0), LandType.WATER)

    def test_is_clear(self):
        self.assertTrue(self.map.is_clear(0, 0))
        self.assertFalse(self.map.is_clear(1, 0))   # 水域
        self.assertFalse(self.map.is_clear(1, 1))   # 未探索
        self.assertFalse(self.map.is_clear(9, 9))   # 越界

    def test_out_of_range_defaults_to_shrouded(self):
        # 缺列时按「未探索」处理，宁可拒绝也不要误判为可见
        empty = MapData(width=2, height=2, columns={})
        self.assertTrue(empty.shrouded(0, 0))
        self.assertFalse(empty.is_clear(0, 0))

    def test_iter_cells(self):
        self.assertEqual(len(list(self.map.iter_cells())), 4)


class TestMapDataApply(unittest.TestCase):
    """增量回填：服务端只在格子变化时发送，且带 index 与 shrouded。"""

    def setUp(self):
        self.map = MapData.parse(build_map_soa(
            width=2, height=2,
            shrouded=[1, 1, 1, 1],
            land=[LandType.ROCK] * 4))

    def test_applies_shrouded_and_land(self):
        cell = parse_cell(build_cell(0, land_type=LandType.CLEAR, shrouded=False))
        self.assertTrue(self.map.apply(cell))
        self.assertFalse(self.map.shrouded(0, 0))
        self.assertEqual(self.map.land_type(0, 0), LandType.CLEAR)
        self.assertTrue(self.map.shrouded(1, 0))    # 邻格不受影响

    def test_applies_row_major_index(self):
        cell = parse_cell(build_cell(2, land_type=LandType.ROAD, shrouded=False))
        self.map.apply(cell)
        self.assertFalse(self.map.shrouded(0, 1))
        self.assertEqual(self.map.land_type(0, 1), LandType.ROAD)

    def test_rejects_out_of_range_index(self):
        cell = parse_cell(build_cell(99, shrouded=False))
        self.assertFalse(self.map.apply(cell))

    def test_apply_all_counts(self):
        cells = [parse_cell(build_cell(0, shrouded=False)),
                 parse_cell(build_cell(1, shrouded=False)),
                 parse_cell(build_cell(99, shrouded=False))]
        self.assertEqual(self.map.apply_all(cells), 2)

    def test_explored_flag_is_monotonic(self):
        # 实测：shrouded 只从真变假，从不回退
        self.map.apply(parse_cell(build_cell(0, shrouded=False)))
        self.map.apply(parse_cell(build_cell(0, shrouded=True)))
        self.assertFalse(self.map.shrouded(0, 0))


class TestTypeTable(unittest.TestCase):
    def setUp(self):
        self.table = TypeTable.parse(build_type_table([
            ("Grizzly Battle Tank", 700, 9, 0x901, AbstractType.UNITTYPE),
            ("Allied Power Plant", 800, 0, 0x902, AbstractType.BUILDINGTYPE),
            ("Allied Construction Yard", 3000, 2, 0x903,
             AbstractType.BUILDINGTYPE),
        ]))

    def test_len(self):
        self.assertEqual(len(self.table), 3)

    def test_name_by_pointer(self):
        self.assertEqual(self.table.name(0x901), "Grizzly Battle Tank")
        self.assertEqual(self.table.name(0x999), "?")

    def test_name_by_object(self):
        obj = GameState.parse(build_game_state(
            objects=[build_object(0xA1, type_pointer=0x901)])).object(0xA1)
        self.assertEqual(self.table.name(obj), "Grizzly Battle Tank")

    def test_find(self):
        entry = self.table.find("power plant")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.pointer, 0x902)
        self.assertEqual(entry.cost, 800)

    def test_find_respects_rtti(self):
        self.assertIsNone(self.table.find("power plant",
                                          rtti=AbstractType.UNITTYPE))
        self.assertIsNotNone(self.table.find("power plant",
                                             rtti=AbstractType.BUILDINGTYPE))

    def test_find_missing(self):
        self.assertIsNone(self.table.find("nonexistent"))


if __name__ == "__main__":
    unittest.main()


class TestHousePowerAndInfiltration(unittest.TestCase):
    """电力与渗透。这三方渗透标志只说明「当前」处于被渗透状态。"""

    def parse(self, **kwargs):
        state = GameState.parse(build_game_state(
            houses=[build_house(PLAYER_HOUSE, current_player=True, **kwargs)]))
        return state.player_house()

    def test_power_output_and_drain(self):
        house = self.parse(power_output=200, power_drain=50)
        self.assertEqual(house.power_output, 200)
        self.assertEqual(house.power_drain, 50)
        self.assertFalse(house.is_low_power)

    def test_short_power_is_flagged(self):
        self.assertTrue(self.parse(power_output=100, power_drain=150).is_low_power)

    def test_equal_power_is_not_short(self):
        self.assertFalse(self.parse(power_output=100, power_drain=100).is_low_power)

    def test_starting_credits_are_parsed(self):
        state = GameState.parse(build_game_state(
            houses=[build_house(PLAYER_HOUSE, current_player=True)]))
        self.assertEqual(state.player_house().start_credits, 0, "fixture 没设，故为 0")

    def test_infiltration_flags(self):
        self.assertFalse(self.parse().is_infiltrated)
        self.assertTrue(self.parse(infiltrated=("allied",)).allied_infiltrated)
        self.assertTrue(self.parse(infiltrated=("soviet",)).is_infiltrated)
        self.assertTrue(self.parse(infiltrated=("third",)).third_infiltrated)

    def test_flags_are_independent(self):
        house = self.parse(infiltrated=("soviet",))
        self.assertFalse(house.allied_infiltrated)
        self.assertFalse(house.third_infiltrated)


class TestTypeTableResolve(unittest.TestCase):
    """类型解析：技法按注册名说话，而引擎只给显示名。"""

    def table(self, aliases=None):
        from ra2agent.state import ObjectType, TypeTable
        return TypeTable([
            ObjectType(name="Grizzly Battle Tank", cost=700, array_index=1,
                       pointer=0x900, type=AbstractType.UNIT),
            ObjectType(name="Allied Power Plant", cost=800, array_index=2,
                       pointer=0x901, type=AbstractType.BUILDING),
        ], aliases=aliases)

    def test_display_name_resolves(self):
        self.assertEqual(self.table().resolve("Grizzly Battle Tank").pointer, 0x900)

    def test_name_is_case_insensitive(self):
        self.assertEqual(self.table().resolve("grizzly battle tank").pointer, 0x900)

    def test_substring_still_works(self):
        self.assertEqual(self.table().resolve("grizzly").pointer, 0x900)

    def test_registered_name_needs_an_alias(self):
        # 引擎的类型表里没有注册名，故没挂别名时认不出
        self.assertIsNone(self.table().resolve("MTNK"))
        self.assertEqual(self.table(aliases={"MTNK": 0x900}).resolve("MTNK").pointer, 0x900)

    def test_aliases_are_case_insensitive(self):
        self.assertEqual(self.table(aliases={"MTNK": 0x900}).resolve("mtnk").pointer, 0x900)

    def test_add_aliases_counts_the_new_ones(self):
        table = self.table(aliases={"MTNK": 0x900})
        self.assertEqual(table.add_aliases({"MTNK": 0x900, "GAPOWR": 0x901}), 1)

    def test_rtti_narrows_the_search(self):
        table = self.table()
        self.assertIsNone(table.resolve("Allied", rtti=AbstractType.UNIT))
        self.assertEqual(table.resolve("Allied", rtti=AbstractType.BUILDING).pointer, 0x901)

    def test_empty_needle_resolves_to_nothing(self):
        self.assertIsNone(self.table().resolve(""))
        self.assertIsNone(self.table().resolve(None))

    def test_unknown_name_resolves_to_nothing(self):
        self.assertIsNone(self.table().resolve("Nonexistent Thing"))
