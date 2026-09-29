"""发送前校验的测试。

校验层是本项目唯一能阻止「越界坐标崩溃游戏」的东西，因此每个拒绝分支都要有
用例覆盖，且合法输入不得被误拒。
"""
import unittest

from ra2agent.constants import (LEPTONS_PER_CELL, AbstractType, LandType,
                                Mission, UnitAction)
from ra2agent.errors import InvalidCommand
from ra2agent.state import GameState, MapData, cell_center
from ra2agent.validate import Validator
from tests.fixtures import (ENEMY_HOUSE, NEUTRAL_HOUSE, PLAYER_HOUSE,
                            build_game_state, build_house, build_map_soa,
                            build_object)

CLEAR_OBJECT = 0xA1
BUILDING_OBJECT = 0xA2
LIMBO_OBJECT = 0xA3
ENEMY_OBJECT = 0xB1
NEUTRAL_OBJECT = 0xC1

MAP_SIDE = 4


def make_map(side=MAP_SIDE):
    """一张 side×side 的地图，全部已探索且为 Clear。"""
    cells = side * side
    return MapData.parse(build_map_soa(
        width=side, height=side,
        shrouded=[0] * cells,
        land=[LandType.CLEAR] * cells))


def make_state():
    """含一个可指挥单位、一个建造中的建筑、一个 limbo 对象与一个敌方单位。"""
    return GameState.parse(build_game_state(
        houses=[build_house(PLAYER_HOUSE, current_player=True),
                build_house(ENEMY_HOUSE)],
        objects=[
            build_object(CLEAR_OBJECT, mission=Mission.GUARD),
            build_object(BUILDING_OBJECT, object_type=AbstractType.BUILDING,
                         mission=Mission.CONSTRUCTION),
            build_object(LIMBO_OBJECT, in_limbo=True),
            build_object(ENEMY_OBJECT, house=ENEMY_HOUSE,
                         object_type=AbstractType.INFANTRY),
        ]))


class TestCoordinates(unittest.TestCase):
    def setUp(self):
        self.validator = Validator(make_map())

    def test_accepts_inside(self):
        for cell in [(0, 0), (1, 1), (3, 3)]:
            with self.subTest(cell=cell):
                self.validator.check_coordinates(cell_center(*cell))

    def test_rejects_at_limit(self):
        limit = MAP_SIDE * LEPTONS_PER_CELL
        with self.assertRaises(InvalidCommand):
            self.validator.check_coordinates(cell_center(0, 0).__class__(limit, 0))
        with self.assertRaises(InvalidCommand):
            self.validator.check_coordinates(cell_center(0, 0).__class__(0, limit))

    def test_rejects_negative(self):
        # -1 会被 Coord2Cell 截断成格 0，即地图内，故必须显式拒绝
        from ra2agent.state import Coordinates
        with self.assertRaises(InvalidCommand):
            self.validator.check_coordinates(Coordinates(-1, 100))
        with self.assertRaises(InvalidCommand):
            self.validator.check_coordinates(Coordinates(100, -1))

    def test_rejects_huge(self):
        from ra2agent.state import Coordinates
        with self.assertRaises(InvalidCommand):
            self.validator.check_coordinates(Coordinates(10_000_000, 100))

    def test_rejects_without_map(self):
        from ra2agent.state import Coordinates
        with self.assertRaises(InvalidCommand):
            Validator().check_coordinates(Coordinates(100, 100))


class TestObjects(unittest.TestCase):
    def setUp(self):
        self.validator = Validator(make_map())
        self.state = make_state()

    def test_resolve_returns_objects(self):
        found = self.validator.resolve(self.state, [CLEAR_OBJECT])
        self.assertEqual([o.pointer for o in found], [CLEAR_OBJECT])

    def test_resolve_accepts_object_instances(self):
        obj = self.state.object(CLEAR_OBJECT)
        self.assertEqual(self.validator.resolve(self.state, [obj])[0], obj)

    def test_rejects_empty(self):
        with self.assertRaises(InvalidCommand):
            self.validator.resolve(self.state, [])

    def test_rejects_unknown_pointer(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.resolve(self.state, [0xDEADBEEF])
        self.assertIn("不在当前状态", str(ctx.exception))

    def test_rejects_limbo(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.resolve(self.state, [LIMBO_OBJECT])
        self.assertIn("limbo", str(ctx.exception))

    def test_rejects_non_state(self):
        with self.assertRaises(InvalidCommand):
            self.validator.resolve(None, [CLEAR_OBJECT])


class TestActions(unittest.TestCase):
    def setUp(self):
        self.validator = Validator(make_map())
        self.state = make_state()

    def test_rejects_unimplemented_action(self):
        for action in (UnitAction.NONE, UnitAction.UNSELECT,
                       UnitAction.TRY_TO_DEPLOY):
            with self.subTest(action=action):
                with self.assertRaises(InvalidCommand):
                    self.validator.check_action(action)

    def test_accepts_implemented_actions(self):
        from ra2agent.constants import UNIT_ACTIONS_IMPLEMENTED
        for action in UNIT_ACTIONS_IMPLEMENTED:
            with self.subTest(action=action):
                self.validator.check_action(action)

    def test_accepts_stop(self):
        self.validator.check_unit_order(self.state, [CLEAR_OBJECT],
                                        UnitAction.STOP)

    def test_rejects_move_without_coordinates(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_unit_order(self.state, [CLEAR_OBJECT],
                                            UnitAction.MOVE)
        self.assertIn("coordinates", str(ctx.exception))

    def test_accepts_move_with_coordinates(self):
        self.validator.check_unit_order(self.state, [CLEAR_OBJECT],
                                        UnitAction.MOVE,
                                        coordinates=cell_center(1, 1))

    def test_rejects_attack_without_target(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_unit_order(self.state, [CLEAR_OBJECT],
                                            UnitAction.ATTACK)
        self.assertIn("target_object", str(ctx.exception))

    def test_accepts_attack_with_target(self):
        self.validator.check_unit_order(self.state, [CLEAR_OBJECT],
                                        UnitAction.ATTACK,
                                        target_object=ENEMY_OBJECT)

    def test_rejects_illegal_mission(self):
        # 建造中的建筑不能被 UnitOrder 指挥，应改走 ClickEvent
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_unit_order(self.state, [BUILDING_OBJECT],
                                            UnitAction.STOP)
        self.assertIn("mission", str(ctx.exception))

    def test_rejects_out_of_map_coordinates(self):
        from ra2agent.state import Coordinates
        with self.assertRaises(InvalidCommand):
            self.validator.check_unit_order(
                self.state, [CLEAR_OBJECT], UnitAction.MOVE,
                coordinates=Coordinates(999_999, 999_999))


class TestOwnership(unittest.TestCase):
    """引擎不拦越权指挥，适配层必须自己拦。

    `UnitOrder` 在全局对象表里按指针查对象，查到即调 `ClickMission`，全程不看
    归属，故敌方与中立单位同样能下令。生产与建造倒是固定归属当前玩家，因为那条
    路走 `add_event`。
    """

    def setUp(self):
        self.validator = Validator(make_map())
        self.state = make_state()

    def test_rejects_enemy_object(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_unit_order(self.state, [ENEMY_OBJECT],
                                            UnitAction.STOP)
        self.assertIn("不是己方", str(ctx.exception))

    def test_rejects_neutral_object(self):
        neutral_state = GameState.parse(build_game_state(
            houses=[build_house(PLAYER_HOUSE, current_player=True),
                    build_house(NEUTRAL_HOUSE, faction="Neutral")],
            objects=[build_object(NEUTRAL_OBJECT, house=NEUTRAL_HOUSE)]))
        with self.assertRaises(InvalidCommand):
            self.validator.check_unit_order(neutral_state, [NEUTRAL_OBJECT],
                                            UnitAction.STOP)

    def test_accepts_own_object(self):
        self.validator.check_unit_order(self.state, [CLEAR_OBJECT],
                                        UnitAction.STOP)

    def test_rejects_mixed_batch(self):
        # 一条命令带多个对象时，只要有一个非己方就整体拒绝
        with self.assertRaises(InvalidCommand):
            self.validator.check_unit_order(
                self.state, [CLEAR_OBJECT, ENEMY_OBJECT], UnitAction.STOP)

    def test_allow_foreign_opts_out(self):
        permissive = Validator(make_map(), allow_foreign=True)
        permissive.check_unit_order(self.state, [ENEMY_OBJECT], UnitAction.STOP)

    def test_with_map_preserves_permissive_policy(self):
        permissive = Validator(make_map(), allow_foreign=True)
        rebuilt = permissive.with_map(make_map())
        self.assertTrue(rebuilt.allow_foreign)
        rebuilt.check_unit_order(self.state, [ENEMY_OBJECT], UnitAction.STOP)

    def test_with_map_preserves_strict_default(self):
        strict = Validator(make_map())
        self.assertFalse(strict.with_map(make_map()).allow_foreign)

    def test_ownership_checked_before_mission(self):
        # 建造中的建筑属己方，报的应是 mission 而不是归属
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_unit_order(self.state, [BUILDING_OBJECT],
                                            UnitAction.STOP)
        self.assertIn("mission", str(ctx.exception))


class TestSellCell(unittest.TestCase):
    def setUp(self):
        self.validator = Validator(make_map())
        self.state = make_state()

    def test_accepts_without_objects(self):
        # SELL_CELL 针对格子，不需要 object_addresses
        self.validator.check_unit_order(self.state, [], UnitAction.SELL_CELL,
                                        coordinates=cell_center(2, 2))

    def test_rejects_without_coordinates(self):
        with self.assertRaises(InvalidCommand):
            self.validator.check_unit_order(self.state, [], UnitAction.SELL_CELL)

    def test_rejects_out_of_map(self):
        from ra2agent.state import Coordinates
        with self.assertRaises(InvalidCommand):
            self.validator.check_unit_order(self.state, [],
                                            UnitAction.SELL_CELL,
                                            coordinates=Coordinates(-5, 0))


class TestClickEvent(unittest.TestCase):
    """对象级网络事件：与 UnitOrder 的差别只有一条——不检查 mission。

    它存在的理由正是处理 `Mission_Construction` 的对象（刚放置的建筑要变卖），
    故存在性与归属照查，mission 不查。
    """

    def setUp(self):
        self.validator = Validator(make_map())
        self.state = make_state()

    def test_accepts_construction_object(self):
        self.validator.check_click_event(self.state, [BUILDING_OBJECT])

    def test_rejects_foreign_object(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_click_event(self.state, [ENEMY_OBJECT])
        self.assertIn("不是己方", str(ctx.exception))

    def test_rejects_unknown_pointer(self):
        with self.assertRaises(InvalidCommand):
            self.validator.check_click_event(self.state, [0xDEADBEEF])

    def test_rejects_limbo(self):
        with self.assertRaises(InvalidCommand) as ctx:
            self.validator.check_click_event(self.state, [LIMBO_OBJECT])
        self.assertIn("limbo", str(ctx.exception))

    def test_allow_foreign_opts_out(self):
        permissive = Validator(make_map(), allow_foreign=True)
        permissive.check_click_event(self.state, [ENEMY_OBJECT])


class TestPlace(unittest.TestCase):
    def test_rejects_out_of_map(self):
        from ra2agent.state import Coordinates
        validator = Validator(make_map())
        with self.assertRaises(InvalidCommand):
            validator.check_place(Coordinates(0, 999_999))

    def test_accepts_inside(self):
        Validator(make_map()).check_place(cell_center(2, 2))


if __name__ == "__main__":
    unittest.main()
