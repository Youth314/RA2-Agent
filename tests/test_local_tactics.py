"""建造链的闭环测试：从「读局势拿落点」到「L0 收到 Place」。

这条链此前断在 R1：技法拿不到 limbo 建筑的 agent id，故谁也发不出一条 `Place`。
本文件只走离线假件，不碰游戏。
"""
import unittest

from ra2agent.command import Commander
from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.errors import CommandFailed
from ra2agent.executor import Executor
from ra2agent.identity import IdentityTable
from ra2agent.intents import Place
from ra2agent.observation import Observation
from ra2agent.state import GameState, MapData, TypeTable, cell_center
from ra2agent.tactics import TacticRegistry
from ra2agent.tactics.conditions import check_conditions
from ra2agent.wake import WakeBridge
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_factory,
                            build_game_state, build_house, build_map_soa,
                            build_object, build_type_table)

SIDE = 9
YARD = 0xC1
PENDING = 0xC2
BUILDING_POINTER = 0xC1            # 类型表里那个建筑条目的指针
BUILDING_NAME = "Allied Power Plant"


def at(cell):
    return cell[0] * 256 + 128, cell[1] * 256 + 128


def make_map():
    cells = SIDE * SIDE
    return MapData.parse(build_map_soa(width=SIDE, height=SIDE,
                                       shrouded=[0] * cells,
                                       land=[LandType.CLEAR] * cells))


MAP = make_map()


def obj(pointer, cell, object_type, in_limbo=False):
    x, y = at(cell)
    return build_object(pointer, type_pointer=BUILDING_POINTER,
                        house=PLAYER_HOUSE, object_type=object_type,
                        mission=Mission.CONSTRUCTION, x=x, y=y,
                        in_limbo=in_limbo, on_map=not in_limbo)


def state_with_completed_building(frame=100):
    """一辆基地车、一座建造厂，外加一栋完工待放置的建筑。"""
    return GameState.parse(build_game_state(
        frame=frame,
        houses=[build_house(PLAYER_HOUSE, current_player=True),
                build_house(ENEMY_HOUSE)],
        factories=[build_factory(PLAYER_HOUSE, PENDING, timer=54)],
        objects=[obj(YARD, (3, 3), AbstractType.BUILDING),
                 obj(PENDING, (3, 3), AbstractType.BUILDING, in_limbo=True)]))


def make_types():
    return TypeTable.parse(build_type_table([
        (BUILDING_NAME, 800, 0, BUILDING_POINTER, AbstractType.BUILDINGTYPE)]))


class FakeClient:
    """记录 `PlaceQuery` 与 `PlaceBuilding` 的假客户端。"""

    def __init__(self, legal=((4, 3),), fail_place=False):
        self.legal = tuple(legal)
        self.fail_place = fail_place
        self.queries = []
        self.placed = []

    def place_query(self, entry, house, candidates, **kwargs):
        self.queries.append({"entry": entry, "house": house,
                             "candidates": tuple(candidates)})
        return [cell_center(x, y) for x, y in self.legal]

    def place_building(self, building, coordinates, **kwargs):
        self.placed.append((building, coordinates))
        if self.fail_place:
            raise CommandFailed("proximity check failed",
                                command_type="PlaceBuilding",
                                reason="placement_blocked")
        from ra2agent.client import CommandResult
        return CommandResult(type="PlaceBuilding", payload=b"", code=None,
                             error="")


class FakeObserver:
    def __init__(self, state, client, types):
        self.identity = IdentityTable()
        self.identity.update(state)
        self.map_data = MAP
        self.types = types
        self.client = client
        self.observation = None
        self.events = None

    def poll(self):
        return self.observation


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def execute(self, intent, state):
        raise AssertionError("本测试不该真的下发命令")


class FakeLayer:
    """够 `Commander` 用的最小技法层。"""

    def __init__(self, registry, state):
        self.registry = registry
        self.completed = []
        self.notices = []
        self.executor = FakeExecutor()
        self.log = None
        # 真实桥件：`status` 会读 `wake.records` 与 `autopilot.records`
        self.wake = WakeBridge(poster=lambda *args, **kwargs: (True, "ok"))
        self._state = state

    def progress(self):
        return ()

    def assign(self, call, observation):
        raise AssertionError("本测试只验受理，不建编队")


class TestBuildChain(unittest.TestCase):
    """R1 + 安全版 R2 的闭环。"""

    def setUp(self):
        self.state = state_with_completed_building()
        self.client = FakeClient()
        self.observer = FakeObserver(self.state, self.client, make_types())
        self.observation = Observation(
            frame=self.state.frame, house=self.state.player_house(),
            own=tuple(o for o in self.state.objects
                      if o.house == PLAYER_HOUSE and not o.in_limbo),
            visible_enemies=(), neutral=(), state=self.state, map_data=MAP,
            types=self.observer.types)
        self.observer.observation = self.observation
        # 整库加载、按名字取技法：不 import 具体模块，模块搬了家这里也不会断
        self.registry = TacticRegistry().load_builtin()
        self.layer = FakeLayer(self.registry, self.state)
        self.commander = Commander(self.layer, self.observer)

    def test_status_offers_a_site_for_the_pending_building(self):
        report = self.commander.status()
        self.assertEqual(len(report.placement), 1)
        self.assertEqual(report.sites, ((4, 3),))
        self.assertIn("可选落点：(4,3)", report.render())

    def test_model_call_reaches_a_place_intent(self):
        """模型一条 call 就能做到放置——不必给技法硬编码落点。"""
        report = self.commander.status()
        cell = report.sites[0]
        dataset = self.registry.run("place_ready_building",
                                    observation=self.observation,
                                    subject=self._pool(),
                                    params={"cell": list(cell)},
                                    frame=self.state.frame)
        self.assertEqual(len(dataset), 1)
        self.assertIsInstance(dataset[0], Place)
        self.assertEqual(dataset[0].cell, cell)

    def test_condition_blocks_when_nothing_is_pending(self):
        empty = GameState.parse(build_game_state(
            houses=[build_house(PLAYER_HOUSE, current_player=True)],
            objects=[obj(YARD, (3, 3), AbstractType.BUILDING)]))
        # 条件只看局面，故观测要与局面配套——不能借「有待放置建筑」的那一份
        observation = Observation(
            frame=empty.frame, house=empty.player_house(),
            own=tuple(o for o in empty.objects
                      if o.house == PLAYER_HOUSE and not o.in_limbo),
            visible_enemies=(), neutral=(), state=empty, map_data=MAP,
            types=self.observer.types)
        self.assertEqual(check_conditions(("has_pending_building",),
                                          _context(observation, self._pool(empty))),
                         ("has_pending_building",))

    def test_condition_passes_when_a_building_waits(self):
        self.assertEqual(check_conditions(("has_pending_building",),
                                          _context(self.observation, self._pool())),
                         ())

    def test_cell_may_be_omitted(self):
        """`cell` 可省：意图带 `cell=None`，由 L0 问 `PlaceQuery` 要一格合法落点。

        以前是技法自己围着待放建筑猜一格，猜出来的格引擎未必认（`CanPlaceHere` /
        `Proximity check failed`），故现在一律交给能问引擎的 L0。
        """
        dataset = self.registry.run("place_ready_building",
                                    observation=self.observation,
                                    subject=self._pool(),
                                    params={}, frame=self.state.frame)
        self.assertEqual(len(dataset), 1)
        self.assertIsInstance(dataset[0], Place)
        self.assertEqual(dataset[0].building, self._agent())
        self.assertIsNone(dataset[0].cell)

    def test_bad_cell_shape_is_rejected_by_the_registry(self):
        """形状不对的参数当场报错，不要等技法里抛 KeyError。"""
        from ra2agent.errors import TacticError
        with self.assertRaises(TacticError):
            self.registry.run("place_ready_building",
                              observation=self.observation, subject=self._pool(),
                              params={"cell": [1, 2, 3]}, frame=self.state.frame)

    def test_executor_routes_the_place_intent(self):
        """L0 照旧只负责把意图翻成命令：不需要为放置新增任何选路。"""
        from ra2agent.validate import Validator
        executor = Executor(self.client, self.observer.identity,
                            types=self.observer.types,
                            validator=Validator(MAP),
                            read_state=lambda: self.state)
        intent = Place(building=self._agent(), cell=(4, 3),
                       created_frame=self.state.frame)
        plan = executor.plan(intent, self.state)
        self.assertEqual(plan.command, "PlaceBuilding")
        self.assertEqual(plan.pointers, (PENDING,))
        self.assertEqual(plan.coordinates, cell_center(4, 3))

    def _executor(self):
        from ra2agent.validate import Validator
        return Executor(self.client, self.observer.identity,
                        types=self.observer.types,
                        validator=Validator(MAP),
                        read_state=lambda: self.state)

    def test_executor_asks_the_engine_when_no_cell_is_given(self):
        """`cell=None`：L0 用 `PlaceQuery` 要一格，模型不必自己算坐标。

        这条链以前是技法自己猜格，猜出来的格引擎未必认——实测给出 `格=(1,0)` 被
        `Proximity check failed` 拒。合法性只有引擎说了算，故问它的动作放在 L0。
        """
        intent = Place(building=self._agent(), cell=None,
                       created_frame=self.state.frame)
        plan = self._executor().plan(intent, self.state)
        self.assertEqual(plan.command, "PlaceBuilding")
        self.assertEqual(plan.coordinates, cell_center(4, 3))
        # 确实问过引擎，且用的是引擎返回的那一格
        self.assertEqual(len(self.client.queries), 1)
        self.assertEqual(self.client.queries[0]["house"].pointer, PLAYER_HOUSE)

    def test_executor_reports_when_the_engine_offers_no_site(self):
        """引擎一个合法格都不给：报清楚的话，不发一条注定的命令。"""
        from ra2agent.errors import InvalidCommand
        self.client.legal = ()
        intent = Place(building=self._agent(), cell=None,
                       created_frame=self.state.frame)
        with self.assertRaises(InvalidCommand) as caught:
            self._executor().plan(intent, self.state)
        self.assertIn("合法落点", str(caught.exception))

    # ------------------------------------------------------------ 辅助
    def _pool(self, state=None):
        from ra2agent.command import UnitPool
        state = state or self.state
        observation = self.observation if state is self.state else Observation(
            frame=state.frame, house=state.player_house(),
            own=tuple(o for o in state.objects
                      if o.house == PLAYER_HOUSE and not o.in_limbo),
            visible_enemies=(), neutral=(), state=state, map_data=MAP,
            types=self.observer.types)
        return UnitPool(observation, self.observer.identity)

    def _agent(self):
        return self.observer.identity.agent_id(PENDING)


def _context(observation, subject):
    """只够评条件用的上下文。"""
    from ra2agent.tactics.core import Tactic, TacticContext, TacticInfo, _Budget
    info = TacticInfo(name="probe", summary="探针")
    return TacticContext(
        registry=None, tactic=Tactic(info=info, run=lambda context: ()),
        observation=observation, subject=subject, params={}, frame=0, memo={},
        log=None, chain=("probe",), attempt=0, budget=_Budget(0))


if __name__ == "__main__":
    unittest.main()
