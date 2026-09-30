"""新增动作类技法的单元测试：生产、放置、集火、区域防守。

只装被测模块的 `TACTICS`，不整库加载——这样某个模块坏掉时失败的测试能直接指到它。
技法全都不碰游戏：观测与局面都是造出来的。
"""
import unittest

from ra2agent.constants import AbstractType
from ra2agent.errors import TacticDenied, TacticError
from ra2agent.runtime.intents import Attack, Hold, Place, Produce
from ra2agent.engine.observation import Observation
from ra2agent.engine.state import (GameState, House, ObjectType, TypeTable, parse_object)
from ra2agent.tactics import TacticRegistry
from ra2agent.tactics.builtin import combat, construction, production
from tests.fixtures import (build_factory, build_game_state, build_house,
                            build_map_soa, build_object)

#: 一格多少 lepton（`Coordinates.cell` 的除数）。
LEPTONS = 256

PLAYER = 0x1000
ENEMY = 0x2000
MTNK = 0x900
GAPOWR = 0x901
YARD = 0x902
FACTORY_OBJECT = 0x601
ENEMY_UNIT = 0x501


class FakeSubject:
    """技法看到的编队视图；敌我都能按 agent id 取。"""

    def __init__(self, agents=(1, 2), objects=None, pointers=None):
        self._agents = tuple(agents)
        self._objects = objects or {}
        self._pointers = pointers or {}

    def agents(self):
        return self._agents

    def object_of(self, agent_id):
        return self._objects.get(agent_id)

    def agent_id(self, pointer):
        return self._pointers.get(pointer)


def unit(pointer, cell, house=PLAYER, type_pointer=MTNK,
         object_type=AbstractType.UNIT, in_limbo=False):
    """把一个对象放在格 `cell` 上。"""
    return build_object(pointer, type_pointer=type_pointer, house=house,
                        object_type=object_type, in_limbo=in_limbo,
                        x=cell[0] * LEPTONS, y=cell[1] * LEPTONS)


def state(*, money=10000, objects=(), factories=()):
    """只含一个己方阵营的局面。"""
    return GameState.parse(build_game_state(
        houses=[build_house(PLAYER, current_player=True, money=money)],
        objects=objects, factories=factories))


def types_table():
    """带注册名别名的类型表。"""
    return TypeTable([
        ObjectType(name="Grizzly Battle Tank", cost=700, array_index=1,
                   pointer=MTNK, type=1),
        ObjectType(name="Allied Power Plant", cost=800, array_index=2,
                   pointer=GAPOWR, type=2),
        ObjectType(name="Allied Construction Yard", cost=2500, array_index=3,
                   pointer=YARD, type=2),
    ], aliases={"MTNK": MTNK, "GAPOWR": GAPOWR, "GACNST": YARD})


def observation(*, state_=None, enemies=(), map_data=None, types=None):
    """一帧最小观测。"""
    house = House(pointer=PLAYER, array_index=0, name="me", faction="Alliance",
                  money=0, current_player=True, is_human_player=True,
                  defeated=False, is_winner=False, is_loser=False)
    return Observation(frame=100, house=house, own=(),
                       visible_enemies=tuple(enemies), neutral=(),
                       state=state_, map_data=map_data, types=types)


def make_map(side=48):
    """全 CLEAR、未遮蔽的地图。要盖得住 (20, 20) 附近的兜底落点。"""
    from ra2agent.constants import LandType
    from ra2agent.engine.state import MapData
    return MapData.parse(build_map_soa(
        width=side, height=side, shrouded=[0] * (side * side),
        land=[LandType.CLEAR] * (side * side)))


def registry(*modules):
    """把草稿模块的技法装进一个临时注册表。"""
    out = TacticRegistry()
    for module in modules:
        out.load(module.TACTICS)
    return out


# ---------------------------------------------------------------- 生产

#: 不给 `types` 时的哨兵：区分「用默认表」与「故意不给表」。
DEFAULT_TYPES = object()


class TestProduction(unittest.TestCase):
    """`train_unit` / `build_structure`。"""

    def run_(self, name, params, *, subject=None, state_=None,
             types=DEFAULT_TYPES, observation_=None):
        table = types_table() if types is DEFAULT_TYPES else types
        return registry(production).run(
            name, observation=observation_ or observation(
                state_=state_ if state_ is not None else state(
                    objects=[unit(YARD, (10, 10), type_pointer=YARD,
                                  object_type=AbstractType.BUILDING)]),
                types=table),
            subject=subject or FakeSubject(), params=params, frame=100)

    def test_produces_the_requested_type(self):
        intents = self.run_("train_unit", {"type": "MTNK"})
        self.assertEqual([i.kind for i in intents], ["produce"])
        self.assertEqual(intents[0].type_pointer, MTNK)
        self.assertEqual(intents[0].type_name, "MTNK")
        # 意图带着这次点名的单位：运行时据此把任务当拍结算、把单位交还
        self.assertEqual(intents[0].scope.objects, (1, 2))

    def test_display_name_works_too(self):
        intents = self.run_("train_unit", {"type": "Grizzly Battle Tank"})
        self.assertEqual([i.type_pointer for i in intents], [MTNK])

    def test_unknown_type_is_denied_by_can_afford(self):
        # 认不出的类型在 `can_afford` 那里就判否：解析不出类型 = 买不起
        with self.assertRaises(TacticDenied):
            self.run_("train_unit", {"type": "NoSuchUnit"})

    def test_missing_table_is_denied_by_can_afford(self):
        # 没有类型表同样过不了 `can_afford`，调用在受理阶段就被拒
        with self.assertRaises(TacticDenied):
            self.run_("train_unit", {"type": "MTNK"}, types=None)

    def test_queued_type_is_not_ordered_twice(self):
        state_ = state(objects=[unit(YARD, (10, 10), type_pointer=YARD,
                                     object_type=AbstractType.BUILDING)],
                       factories=[build_factory(PLAYER, FACTORY_OBJECT,
                                                queued=(MTNK,))])
        with self.assertRaises(TacticError):
            self.run_("train_unit", {"type": "MTNK"}, state_=state_)

    def test_not_enough_money_is_denied_by_can_afford(self):
        with self.assertRaises(TacticDenied):
            self.run_("train_unit", {"type": "MTNK"},
                      state_=state(money=100,
                                   objects=[unit(YARD, (10, 10), type_pointer=YARD,
                                                 object_type=AbstractType.BUILDING)]))

    def test_missing_param_is_rejected(self):
        with self.assertRaises(TacticError):
            self.run_("train_unit", {})

    def test_build_structure_needs_a_construction_yard(self):
        # 只有兵、没有建造厂：条件不满足，调用被拒
        with self.assertRaises(TacticDenied):
            self.run_("build_structure", {"type": "GAPOWR"},
                      state_=state(objects=[unit(0x701, (10, 10))]))

    def test_build_structure_passes_with_a_yard(self):
        intents = self.run_("build_structure", {"type": "GAPOWR"})
        self.assertEqual([i.type_pointer for i in intents], [GAPOWR])


# ---------------------------------------------------------------- 放置

class TestPlaceReadyBuilding(unittest.TestCase):
    """`place_ready_building`。"""

    def setup_state(self, *, completed=True):
        timer = 54 if completed else 1
        return state(objects=[unit(FACTORY_OBJECT, (20, 20), type_pointer=GAPOWR,
                                   object_type=AbstractType.BUILDING,
                                   in_limbo=completed)],
                     factories=[build_factory(PLAYER, FACTORY_OBJECT, timer=timer)])

    def subject(self):
        return FakeSubject(agents=(1,), pointers={FACTORY_OBJECT: 900})

    def run_(self, params, *, state_=None, map_data=None):
        return registry(construction).run(
            "place_ready_building",
            observation=observation(state_=state_ if state_ is not None
                                    else self.setup_state(),
                                    map_data=map_data, types=types_table()),
            subject=self.subject(), params=params, frame=100)

    def test_places_at_the_given_cell(self):
        intents = self.run_({"cell": (21, 21)})
        self.assertEqual([i.kind for i in intents], ["place"])
        self.assertEqual(intents[0].building, 900)
        self.assertEqual(tuple(intents[0].cell), (21, 21))

    def test_leaves_the_cell_to_l0_when_none_given(self):
        """不给落点就交给 L0 去问引擎——技法自己不再猜格。

        猜出来的「空地」会被引擎以 `CanPlaceHere` / `Proximity check failed` 拒
        （实测兜底格给出过 `格=(1,0)`），故合法落点这件事只能在能问引擎的那一层做。
        """
        intents = self.run_({}, map_data=make_map())
        self.assertEqual([i.kind for i in intents], ["place"])
        self.assertIsNone(intents[0].cell)

    def test_without_map_and_without_cell_it_still_places(self):
        """没有地图也照产意图：落点合法性由引擎说了算，不需要本地地图。"""
        intents = self.run_({})
        self.assertEqual([i.kind for i in intents], ["place"])
        self.assertIsNone(intents[0].cell)

    def test_no_pending_building_is_denied(self):
        with self.assertRaises(TacticDenied):
            self.run_({"cell": (21, 21)}, state_=self.setup_state(completed=False))

    def test_bad_cell_shape_is_rejected(self):
        with self.assertRaises(TacticError):
            self.run_({"cell": [1, 2, 3]})

    def test_explicit_none_means_pick_one(self):
        # `cell: None` 等于「没给」，同样交给 L0 找
        intents = self.run_({"cell": None}, map_data=make_map())
        self.assertEqual([i.kind for i in intents], ["place"])
        self.assertIsNone(intents[0].cell)


# ---------------------------------------------------------------- 接战

class TestCombat(unittest.TestCase):
    """`focus_fire` / `guard_area`。"""

    def scene(self):
        """两个己方单位：1 号离敌人两格，2 号在远处。"""
        enemy = parse_object(unit(ENEMY_UNIT, (10, 10), house=ENEMY))
        subject = FakeSubject(
            agents=(1, 2),
            objects={1: parse_object(unit(0x801, (12, 10))),
                     2: parse_object(unit(0x802, (40, 40)))},
            pointers={ENEMY_UNIT: 501})
        return enemy, subject

    def run_(self, name, params, *, enemy=True):
        scene_enemy, subject = self.scene()
        return registry(combat).run(
            name,
            observation=observation(state_=state(), enemies=([scene_enemy] if enemy else [])),
            subject=subject, params=params, frame=100)

    def test_focus_fire_needs_a_target(self):
        """`target` 必填。

        原先默认 0，等于「所有人都驻守」，任务还记成 `satisfied`——模型少写一个
        参数却拿到「成功」，看不出自己什么都没打。
        """
        with self.assertRaises(TacticError):
            self.run_("focus_fire", {})

    def test_focus_fire_attacks_the_named_target(self):
        intents = self.run_("focus_fire", {"target": 501})
        # 够得着的打、够不着的**开过去打**——点名的目标默认去追（实测旧实现把 4 台
        # 坦克原地驻守，玩家不但没打成还整体后撤）
        self.assertEqual([i.kind for i in intents], ["attack", "move_to"])
        self.assertEqual(intents[0].target, 501)
        self.assertEqual(intents[0].units, (1,))
        self.assertEqual(intents[1].stance, "aggressive")

    def test_focus_fire_can_stay_put_instead_of_chasing(self):
        intents = self.run_("focus_fire", {"target": 501, "chase": False})
        self.assertEqual([i.kind for i in intents], ["attack", "hold"])

    def test_focus_fire_holds_everyone_when_target_is_gone(self):
        intents = self.run_("focus_fire", {"target": 501}, enemy=False)
        self.assertEqual([i.kind for i in intents], ["hold", "hold"])

    def test_guard_area_only_orders_units_with_a_target(self):
        # 没有目标的单位不下令：任务留在在管里，下一拍再看
        intents = self.run_("guard_area", {"radius": 8})
        self.assertEqual([i.kind for i in intents], ["attack"])
        self.assertEqual(intents[0].units, (1,))

    def test_guard_area_is_silent_without_enemies(self):
        self.assertEqual(self.run_("guard_area", {"radius": 8}, enemy=False), ())

    def test_guard_area_ignores_targets_outside_the_radius(self):
        self.assertEqual(self.run_("guard_area", {"radius": 1}), ())

    def test_bad_radius_is_rejected(self):
        with self.assertRaises(TacticError):
            self.run_("guard_area", {"radius": 0})


if __name__ == "__main__":
    unittest.main()


class TestGuardExpiry(unittest.TestCase):
    """`guard_area` 靠"不下令"活着，故必须自带边界。"""

    def run_(self, memo, frame, params=None):
        enemy = parse_object(unit(ENEMY_UNIT, (10, 10), house=ENEMY))
        subject = FakeSubject(agents=(1,),
                              objects={1: parse_object(unit(0x801, (12, 10)))},
                              pointers={ENEMY_UNIT: 501})
        return registry(combat).run(
            "guard_area",
            observation=observation(state_=state(), enemies=(enemy,)),
            subject=subject, params=params or {"radius": 8, "max_frames": 100},
            frame=frame, memo=memo)

    def test_keeps_firing_before_the_deadline(self):
        memo = {}
        self.assertEqual([i.kind for i in self.run_(memo, 100)], ["attack"])
        self.assertEqual([i.kind for i in self.run_(memo, 150)], ["attack"])

    def test_falls_back_to_holding_at_the_deadline(self):
        memo = {}
        self.run_(memo, 100)
        # 到点后转驻守：单位 `ARRIVED`，任务结算、单位交还
        self.assertEqual([i.kind for i in self.run_(memo, 200)], ["hold"])

    def test_bad_max_frames_is_rejected(self):
        with self.assertRaises(TacticError):
            self.run_({}, 100, {"radius": 8, "max_frames": 0})
