"""开局、经济、侦察、撤退这批技法的离线测试。

它们全是「技法自己算」的那一类（找矿、找没探过的格、按阶梯补齐建筑），所以测试的
重点是**算法选得对不对**：最近的矿是哪一格、只动停工的矿车、上一件没落地就别下新单。

夹具走真路径：对象先序列化成 proto 再解析，类型表按显示名建，目录按注册名建——
`by_name` 那一跳正是这些技法认类型的地方，绕过它就测不到真东西。
"""
import unittest

from ra2agent.constants import AbstractType, LandType, MISSION_NONE, Mission
from ra2agent.data.catalogue import Catalogue, Entry
from ra2agent.engine.observation import Observation
from ra2agent.engine.state import GameState, MapData, TypeTable
from ra2agent.runtime.intents import MoveTo
from ra2agent.tactics import TacticRegistry
from ra2agent.tactics.builtin.economy import IDLE_MISSIONS, nearest_ore
from ra2agent.tactics.builtin.scouting import nearest_unknown
from tests.fixtures import (PLAYER_HOUSE, build_game_state, build_house,
                            build_map_soa, build_object, build_type_table)
from tests.test_tactics import FakeSubject, run

SIDE = 9
MINER_TYPE, YARD_TYPE, PLANT_TYPE, BARRACKS_TYPE = 0x901, 0x902, 0x903, 0x904
FACTORY_TYPE = 0x905

MINER = ("CMIN", "Chrono Miner")
YARD = ("GACNST", "Allied Construction Yard")
PLANT = ("GAPOWR", "Allied Power Plant")
BARRACKS = ("GAPILE", "Allied Barracks")
FACTORY = ("GAWEAP", "Allied War Factory")

TYPES = ((MINER, MINER_TYPE), (YARD, YARD_TYPE), (PLANT, PLANT_TYPE),
         (BARRACKS, BARRACKS_TYPE), (FACTORY, FACTORY_TYPE))


def at(cell):
    return cell[0] * 256 + 128, cell[1] * 256 + 128


COSTS = {MINER_TYPE: 1400, YARD_TYPE: 2500, PLANT_TYPE: 800,
         BARRACKS_TYPE: 500, FACTORY_TYPE: 2000}


def make_types():
    """类型表：显示名进条目、注册名进 `aliases`（真机由 `attach_type_aliases` 填）。

    `can_afford` 走 `types.resolve(注册名)` 拿价格，故别名不填就一律判「买不起」——
    这是测试夹具必须还原真机的一点。
    """
    table = TypeTable.parse(build_type_table([
        (name, COSTS[pointer], index, pointer,
         AbstractType.UNIT if pointer == MINER_TYPE else AbstractType.BUILDINGTYPE)
        for index, ((_id, name), pointer) in enumerate(TYPES)]))
    table.aliases = {reg_id.lower(): pointer for (reg_id, _name), pointer in TYPES}
    return table


def make_catalogue(*, harvester=True):
    return Catalogue([
        Entry(id="CMIN", name=MINER[1], kind="vehicle", cost=1400, tech_level=1,
              prerequisite=("GAWEAP",), owners=("Alliance",), harvester=harvester),
        Entry(id="GACNST", name=YARD[1], kind="building", cost=2500, tech_level=1,
              prerequisite=(), owners=("Alliance",)),
        Entry(id="GAPOWR", name=PLANT[1], kind="building", cost=800, tech_level=1,
              prerequisite=("GACNST",), owners=("Alliance",)),
        Entry(id="GAPILE", name=BARRACKS[1], kind="building", cost=500, tech_level=1,
              prerequisite=("GACNST",), owners=("Alliance",)),
        Entry(id="GAWEAP", name=FACTORY[1], kind="building", cost=2000, tech_level=1,
              prerequisite=("GACNST", "GAPOWR"), owners=("Alliance",)),
    ])


def make_map(*, ore=(), shrouded=()):
    """一张小地图：指定格有矿 / 被遮蔽（未探索）。"""
    cells = SIDE * SIDE
    tiberium = [0] * cells
    for x, y in ore:
        tiberium[y * SIDE + x] = 100
    shade = [0] * cells
    for x, y in shrouded:
        shade[y * SIDE + x] = 1
    return MapData.parse(build_map_soa(width=SIDE, height=SIDE, shrouded=shade,
                                       land=[LandType.CLEAR] * cells,
                                       tiberium=tiberium))


def miner(pointer, *, mission=Mission.STOP, cell=(4, 4)):
    x, y = at(cell)
    return build_object(pointer, type_pointer=MINER_TYPE, house=PLAYER_HOUSE,
                        object_type=AbstractType.UNIT, mission=mission, x=x, y=y)


def building(pointer, *, type_pointer=YARD_TYPE, cell=(4, 4), in_limbo=False):
    x, y = at(cell)
    return build_object(pointer, type_pointer=type_pointer, house=PLAYER_HOUSE,
                        object_type=AbstractType.BUILDING,
                        mission=Mission.CONSTRUCTION, x=x, y=y, in_limbo=in_limbo,
                        on_map=not in_limbo)


def make_state(objects, *, factories=(), money=5000, drain=0, output=0):
    return GameState.parse(build_game_state(
        houses=[build_house(PLAYER_HOUSE, current_player=True, money=money,
                            power_drain=drain, power_output=output)],
        objects=list(objects), factories=list(factories), frame=100))


def make_observation(state, *, map_data=None, catalogue_=None):
    return Observation(frame=state.frame, house=state.player_house(), own=(),
                       visible_enemies=(), neutral=(), state=state,
                       map_data=map_data, types=make_types(),
                       catalogue=catalogue_ if catalogue_ is not None
                       else make_catalogue())


def subject_of(state, *pointers):
    """主体：全是己方单位时用「全部」，点名时给具体几个。"""
    pointers = pointers or tuple(obj.pointer for obj in state.own_objects())
    agents = {pointer: index + 1 for index, pointer in enumerate(pointers)}
    objects = {agents[p]: state.object(p) for p in pointers}
    back = {p: agents[p] for p in pointers}
    return FakeSubject(agents=tuple(agents.values()), objects=objects, pointers=back)


class TestNearestOre(unittest.TestCase):
    """找矿是纯计算，先单独钉住它。"""

    def test_picks_the_closest_ore(self):
        map_data = make_map(ore=[(0, 0), (3, 3), (1, 8)])
        self.assertEqual(nearest_ore(map_data, (2, 3)), (3, 3))

    def test_ignores_unexplored_ore(self):
        """看不见的矿不该派人去——那是把部队送进黑区。"""
        map_data = make_map(ore=[(3, 3)], shrouded=[(3, 3)])
        self.assertIsNone(nearest_ore(map_data, (2, 3)))

    def test_nothing_in_range_gives_none(self):
        self.assertIsNone(nearest_ore(make_map(ore=[]), (2, 3), radius=3))


class TestNearestUnknown(unittest.TestCase):
    def test_picks_the_closest_unexplored_cell(self):
        map_data = make_map(shrouded=[(0, 0), (5, 1), (8, 8)])
        self.assertEqual(nearest_unknown(map_data, (4, 1)), (5, 1))

    def test_fully_explored_gives_none(self):
        self.assertIsNone(nearest_unknown(make_map(shrouded=[]), (4, 4), radius=3))


class TestHarvest(unittest.TestCase):
    def test_sends_the_named_miner_to_the_nearest_ore(self):
        state = make_state([miner(0xB1)])
        obs = make_observation(state, map_data=make_map(ore=[(6, 4)]))
        unit = state.object(0xB1)
        intents = run(TacticRegistry().load_builtin(), "harvest", observation=obs,
                      subject=subject_of(state, unit.pointer))
        self.assertEqual([i.cell for i in intents], [(6, 4)])
        self.assertEqual(intents[0].stance, "passive", "采矿路上不恋战")

    def test_a_non_harvester_is_left_alone(self):
        state = make_state([miner(0xB1)])
        obs = make_observation(state, map_data=make_map(ore=[(6, 4)]),
                               catalogue_=make_catalogue(harvester=False))
        unit = state.object(0xB1)
        self.assertEqual(run(TacticRegistry().load_builtin(), "harvest",
                             observation=obs,
                             subject=subject_of(state, unit.pointer)), ())


class TestAutoHarvest(unittest.TestCase):
    """自动版只碰停工的矿车——正在采矿的去动它等于让它永远在路上。"""

    def _intents(self, mission, *, frame=100, memo=None, ore=((6, 4),)):
        state = make_state([miner(0xB1, mission=mission)])
        obs = make_observation(state, map_data=make_map(ore=ore))
        unit = state.object(0xB1)
        return TacticRegistry().load_builtin().run(
            "auto_harvest", observation=obs,
            subject=subject_of(state, unit.pointer), frame=frame,
            memo=memo if memo is not None else {})

    def test_a_stopped_miner_is_sent_back_to_ore(self):
        self.assertEqual([i.cell for i in self._intents(Mission.STOP)], [(6, 4)])

    def test_a_harvesting_miner_is_not_disturbed(self):
        self.assertEqual(self._intents(Mission.HARVEST), ())

    def test_a_returning_miner_is_not_disturbed(self):
        self.assertEqual(self._intents(Mission.RETURN), ())

    def test_stop_counts_as_idle(self):
        self.assertIn(Mission.STOP, IDLE_MISSIONS)
        self.assertIn(MISSION_NONE, IDLE_MISSIONS)

    def test_does_not_repeat_the_same_order_every_tick(self):
        """到了却没恢复采矿时，别每拍重发同一条移动令。"""
        memo = {}
        self.assertEqual(len(self._intents(Mission.STOP, frame=100, memo=memo)), 1)
        self.assertEqual(self._intents(Mission.STOP, frame=160, memo=memo), ())


class TestKeepHarvesters(unittest.TestCase):
    def _intents(self, count, params=None):
        # 有重工才谈得上造矿车：`prereq_met` 会按 CMIN 的前提（GAWEAP）判
        objects = ([building(0xA0), building(0xA1, type_pointer=FACTORY_TYPE)]
                   + [miner(0xB0 + i) for i in range(count)])
        state = make_state(objects)
        obs = make_observation(state, map_data=make_map())
        return run(TacticRegistry().load_builtin(), "keep_harvesters",
                   params or {"target": 4}, observation=obs,
                   subject=subject_of(state, 0xA0))

    def test_below_target_orders_one(self):
        self.assertEqual([i.kind for i in self._intents(1)], ["produce"])

    def test_at_target_orders_nothing(self):
        self.assertEqual(self._intents(4), ())


class TestKeepPower(unittest.TestCase):
    def _intents(self, *, drain, output, objects=None):
        objects = objects if objects is not None else [building(0xA0)]
        state = make_state(objects, drain=drain, output=output)
        obs = make_observation(state, map_data=make_map())
        return run(TacticRegistry().load_builtin(), "keep_power", observation=obs,
                   subject=subject_of(state, 0xA0))

    def test_low_power_orders_a_plant(self):
        self.assertEqual([i.kind for i in self._intents(drain=200, output=100)],
                         ["produce"])

    def test_surplus_orders_nothing(self):
        self.assertEqual(self._intents(drain=100, output=200), ())

    def test_a_busy_yard_is_left_alone(self):
        """建造厂正忙（有一栋待放置）时不插队。"""
        objects = [building(0xA0),
                   building(0xD1, type_pointer=PLANT_TYPE, in_limbo=True)]
        self.assertEqual(self._intents(drain=200, output=100, objects=objects), ())


class TestAutoOpening(unittest.TestCase):
    """开局阶梯：一次只造一件，缺哪一级造哪一级。"""

    def _intents(self, objects):
        state = make_state(objects)
        obs = make_observation(state, map_data=make_map())
        return run(TacticRegistry().load_builtin(), "auto_opening", observation=obs,
                   subject=subject_of(state, 0xA0))

    def test_only_a_yard_means_build_the_power_plant(self):
        self.assertEqual([i.kind for i in self._intents([building(0xA0)])],
                         ["produce"])

    def test_a_yard_and_a_plant_means_build_the_barracks(self):
        objects = [building(0xA0), building(0xC2, type_pointer=PLANT_TYPE)]
        self.assertEqual([i.kind for i in self._intents(objects)], ["produce"])

    def test_a_pending_building_holds_the_ladder(self):
        objects = [building(0xA0),
                   building(0xD1, type_pointer=PLANT_TYPE, in_limbo=True)]
        self.assertEqual(self._intents(objects), ())


class TestScoutArea(unittest.TestCase):
    def _intents(self, *, shrouded, params=None):
        state = make_state([miner(0xB1)])
        obs = make_observation(state, map_data=make_map(shrouded=shrouded))
        unit = state.object(0xB1)
        return run(TacticRegistry().load_builtin(), "scout_area", params=params,
                   observation=obs, subject=subject_of(state, unit.pointer))

    def test_heads_for_the_nearest_unexplored_cell(self):
        intents = self._intents(shrouded=[(6, 2)])
        self.assertEqual([i.cell for i in intents], [(6, 2)])
        self.assertEqual(intents[0].stance, "passive", "侦察默认不恋战")

    def test_nothing_left_to_explore_settles(self):
        self.assertEqual(self._intents(shrouded=[], params={"radius": 3}), ())


class TestRetreat(unittest.TestCase):
    def _intents(self, params=None, *, cell=(4, 4)):
        yard = building(0xA0, cell=cell)
        unit = miner(0xB1, mission=Mission.GUARD, cell=(7, 7))
        state = make_state([yard, unit])
        obs = make_observation(state, map_data=make_map())
        return run(TacticRegistry().load_builtin(), "retreat", params=params,
                   observation=obs, subject=subject_of(state, 0xB1))

    def test_falls_back_to_the_base_center(self):
        intents = self._intents()
        self.assertEqual([i.cell for i in intents], [(4, 4)])
        self.assertEqual(intents[0].stance, "passive")

    def test_an_explicit_cell_wins(self):
        self.assertEqual([i.cell for i in self._intents({"cell": (7, 1)})], [(7, 1)])


if __name__ == "__main__":
    unittest.main()
