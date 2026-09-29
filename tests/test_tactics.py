"""技法框架的测试。

覆盖三件事：注册与参数校验、两道闸（可见与可调用）、调用链保险（等级穿透、环、
深度、额度、异常隔离）。技法全是假的，不碰游戏。
"""
import json
import os
import tempfile
import unittest

from ra2agent.errors import TacticDenied, TacticError, TacticFailed
from ra2agent.intents import Hold, Layer, MoveTo, Scope
from ra2agent.observation import Observation
from ra2agent.tactics import (REQUIRED, Card, Level, Mode, Param, Tactic,
                              TacticInfo, TacticPolicy, TacticRegistry)
from ra2agent.tactics.core import TacticContext


class FakeSubject:
    """技法看到的编队视图。"""

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


def make_observation(frame=100, map_data=None, enemies=()):
    """一帧最小观测；只放技法会读到的字段。"""
    from ra2agent.state import House
    house = House(pointer=0x1000, array_index=0, name="me", faction="Alliance",
                  money=0, current_player=True, is_human_player=True,
                  defeated=False, is_winner=False, is_loser=False)
    return Observation(frame=frame, house=house, own=(), visible_enemies=tuple(enemies),
                       neutral=(), state=None, map_data=map_data)


def make_map(side=8, shrouded=None, land=None):
    from ra2agent.constants import LandType
    from ra2agent.state import MapData
    from tests.fixtures import build_map_soa
    cells = side * side
    return MapData.parse(build_map_soa(
        width=side, height=side,
        shrouded=shrouded if shrouded is not None else [0] * cells,
        land=land if land is not None else [LandType.CLEAR] * cells))


def run(registry, name, params=None, *, observation=None, subject=None, frame=100,
        attempt=0):
    """替测试跑一次顶层调用。"""
    return registry.run(name, observation=observation or make_observation(frame),
                        subject=subject or FakeSubject(), params=params or {},
                        frame=frame, attempt=attempt)


# ---------------------------------------------------------------- 注册
class TestRegistration(unittest.TestCase):
    def test_duplicate_name_is_rejected(self):
        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="a", summary="甲"), lambda ctx: ()))
        with self.assertRaises(TacticError):
            registry.register(Tactic(TacticInfo(name="a", summary="乙"), lambda ctx: ()))

    def test_missing_summary_is_rejected(self):
        with self.assertRaises(TacticError):
            TacticRegistry().register(Tactic(TacticInfo(name="a", summary=""),
                                             lambda ctx: ()))

    def test_unknown_name_is_rejected(self):
        with self.assertRaises(TacticError):
            TacticRegistry().get("nope")

    def test_builtin_library_loads(self):
        registry = TacticRegistry().load_builtin()
        self.assertEqual(len(registry), 6)
        self.assertIn("advance_covering", registry.names())
        self.assertIn("hold_and_fire", registry.names())


# ---------------------------------------------------------------- 参数
class TestParameters(unittest.TestCase):
    def setUp(self):
        self.registry = TacticRegistry()
        self.registry.register(Tactic(TacticInfo(
            name="p", summary="带参数的技法",
            params=(Param("cell", REQUIRED, "目标格"),
                    Param("radius", 8, "半径"))), lambda ctx: ()))

    def test_defaults_are_filled(self):
        run(self.registry, "p", {"cell": (1, 2)})

    def test_required_is_enforced(self):
        with self.assertRaises(TacticError) as ctx:
            run(self.registry, "p", {"radius": 3})
        self.assertIn("缺少参数", str(ctx.exception))

    def test_bad_value_is_rejected_by_check(self):
        from ra2agent.tactics import is_cell
        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(
            name="c", summary="带检查的参数",
            params=(Param("cell", REQUIRED, "目标格", is_cell),)),
            lambda ctx: ()))
        for bad in (None, "5,5", (1,), (1, 2, 3), (1.5, 2)):
            with self.subTest(bad=bad):
                with self.assertRaises(TacticError) as ctx:
                    run(registry, "c", {"cell": bad})
                self.assertIn("取值不合法", str(ctx.exception))
        run(registry, "c", {"cell": [1, 2]})          # JSON 往返后是列表

    def test_builtin_rejects_bad_cell(self):
        registry = TacticRegistry().load_builtin()
        with self.assertRaises(TacticError) as ctx:
            run(registry, "advance_to_cell", {"cell": None},
                subject=FakeSubject(), observation=make_observation(map_data=make_map()))
        self.assertIn("取值不合法", str(ctx.exception))

    def test_unknown_parameter_is_rejected(self):
        with self.assertRaises(TacticError) as ctx:
            run(self.registry, "p", {"cell": (1, 2), "typo": 1})
        self.assertIn("不认识参数", str(ctx.exception))


# ---------------------------------------------------------------- 门控
class TestGates(unittest.TestCase):
    def setUp(self):
        self.registry = TacticRegistry()
        self.seen = []
        for name, level, expose in (("normal_t", Level.NORMAL, True),
                                    ("edge_t", Level.EDGE, True),
                                    ("part_t", Level.NORMAL, False)):
            self.registry.register(Tactic(
                TacticInfo(name=name, summary=name, level=level, expose=expose),
                self._spy))

    def _spy(self, context):
        self.seen.append(context.name)
        return ()

    def test_level_above_threshold_blocks_call(self):
        with self.assertRaises(TacticDenied):
            run(self.registry, "edge_t")
        self.assertEqual(self.seen, [])

    def test_raising_the_threshold_allows_it(self):
        registry = TacticRegistry(TacticPolicy(
            max_level={Layer.L1_TACTIC: Level.EDGE}))
        registry.register(Tactic(TacticInfo(name="edge_t", summary="e",
                                            level=Level.EDGE), self._spy))
        run(registry, "edge_t")
        self.assertEqual(self.seen, ["edge_t"])

    def test_disabled_list_blocks_call(self):
        registry = TacticRegistry(TacticPolicy(disabled=frozenset({"normal_t"})))
        registry.register(Tactic(TacticInfo(name="normal_t", summary="n"), self._spy))
        with self.assertRaises(TacticDenied):
            run(registry, "normal_t")

    def test_enabled_list_is_a_whitelist(self):
        registry = TacticRegistry(TacticPolicy(enabled=frozenset({"normal_t"})))
        for name in ("normal_t", "part_t"):
            registry.register(Tactic(TacticInfo(name=name, summary=name), self._spy))
        run(registry, "normal_t")
        with self.assertRaises(TacticDenied):
            run(registry, "part_t")

    def test_parts_are_visible_to_composites_only(self):
        # 零件不进卡片，但仍能被组合技法按名字调用；等级门控对它同样有效
        self.assertNotIn("part_t", [c.name for c in self.registry.cards(Mode.MATCH)])
        run(self.registry, "part_t")
        self.assertEqual(self.seen, ["part_t"])


# ---------------------------------------------------------------- 卡片
class TestCards(unittest.TestCase):
    def setUp(self):
        self.registry = TacticRegistry().load_builtin()
        self.map = make_map()

    def test_match_mode_hides_parts(self):
        names = [c.name for c in self.registry.cards(Mode.MATCH)]
        self.assertNotIn("halt", names)
        self.assertIn("advance_to_cell", names)

    def test_offline_mode_shows_parts(self):
        names = [c.name for c in self.registry.cards(Mode.OFFLINE)]
        self.assertIn("halt", names)

    def test_conditions_filter_by_situation(self):
        # 没有敌人时，接战技法不该出现在卡片里；停止移动不依赖敌人，仍在
        observation = make_observation(map_data=self.map)
        subject = FakeSubject()
        names = [c.name for c in self.registry.cards(Mode.MATCH, observation, subject)]
        self.assertNotIn("engage_nearest", names)
        self.assertIn("advance_covering", names)
        self.assertIn("hold_and_fire", names)

    def test_card_text_is_one_line(self):
        card = Card(name="x", summary="说明", level="normal",
                    params=(Param("radius", 8, "半径"),), requires=("has_map",))
        text = card.text()
        self.assertNotIn("\n", text)
        self.assertIn("radius=8", text)
        self.assertIn("has_map", text)

    def test_catalog_lists_everything(self):
        text = self.registry.catalog()
        for name in self.registry.names():
            self.assertIn(name, text)

    def test_required_parameter_shows_in_card(self):
        card = {c.name: c for c in self.registry.cards(Mode.MATCH)}["advance_to_cell"]
        self.assertIn("cell=必填", card.text())


# ---------------------------------------------------------------- 停止开火
class TestHoldAndFire(unittest.TestCase):
    """停止移动但保持开火：名片与适用条件。行为在 test_micro 与 test_replay。"""

    def setUp(self):
        self.registry = TacticRegistry().load_builtin()

    def test_card_shows_the_fire_radius(self):
        card = {c.name: c for c in self.registry.cards(Mode.MATCH)}["hold_and_fire"]
        self.assertIn("radius=8", card.text())
        self.assertIn("has_units", card.text())

    def test_denied_without_units(self):
        with self.assertRaises(TacticDenied) as ctx:
            run(self.registry, "hold_and_fire", subject=FakeSubject(agents=()))
        self.assertEqual(ctx.exception.kind, "condition")

    def test_bad_radius_is_rejected(self):
        with self.assertRaises(TacticError) as ctx:
            run(self.registry, "hold_and_fire", {"radius": 0})
        self.assertIn("取值不合法", str(ctx.exception))


# ---------------------------------------------------------------- 调用链
class TestCallChain(unittest.TestCase):
    def _registry(self, **policy):
        registry = TacticRegistry(TacticPolicy(**policy))
        return registry

    def test_ctx_call_runs_inner(self):
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="inner", summary="i"),
                                 lambda ctx: (1,)))
        registry.register(Tactic(TacticInfo(name="outer", summary="o"),
                                 lambda ctx: ctx.call("inner")))
        self.assertEqual(run(registry, "outer"), (1,))

    def test_level_is_transitive(self):
        # normal 的外壳调 exploit 的内层，整条链按最高等级算
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="inner", summary="i",
                                            level=Level.EXPLOIT), lambda ctx: (1,)))
        registry.register(Tactic(TacticInfo(name="outer", summary="o"),
                                 lambda ctx: ctx.call("inner")))
        with self.assertRaises(TacticDenied):
            run(registry, "outer")

    def test_cycle_is_rejected(self):
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="a", summary="a"),
                                 lambda ctx: ctx.call("b")))
        registry.register(Tactic(TacticInfo(name="b", summary="b"),
                                 lambda ctx: ctx.call("a")))
        with self.assertRaises(TacticError) as ctx:
            run(registry, "a")
        self.assertIn("环", str(ctx.exception))

    def test_depth_limit(self):
        registry = self._registry(max_depth=2)
        for index in range(4):
            registry.register(Tactic(
                TacticInfo(name=f"t{index}", summary="t"),
                (lambda nxt: (lambda ctx: ctx.call(nxt)))(f"t{index + 1}")))
        registry.register(Tactic(TacticInfo(name="t4", summary="t"), lambda ctx: ()))
        with self.assertRaises(TacticError) as ctx:
            run(registry, "t0")
        self.assertIn("深度", str(ctx.exception))

    def test_call_budget(self):
        registry = self._registry(max_calls=3)
        registry.register(Tactic(TacticInfo(name="leaf", summary="l"),
                                 lambda ctx: ()))
        registry.register(Tactic(TacticInfo(name="fan", summary="f"),
                                 lambda ctx: [ctx.call("leaf") for _ in range(9)]))
        with self.assertRaises(TacticError) as ctx:
            run(registry, "fan")
        self.assertIn("次数", str(ctx.exception))

    def test_optional_call_survives_missing_condition(self):
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="needs", summary="n",
                                            requires=("has_enemies",)),
                                 lambda ctx: (1,)))
        registry.register(Tactic(TacticInfo(name="soft", summary="s"),
                                 lambda ctx: ctx.call("needs", optional=True)))
        self.assertEqual(run(registry, "soft"), ())

    def test_optional_does_not_bypass_level_gate(self):
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="bad", summary="b",
                                            level=Level.EXPLOIT),
                                 lambda ctx: (1,)))
        registry.register(Tactic(TacticInfo(name="soft", summary="s"),
                                 lambda ctx: ctx.call("bad", optional=True)))
        with self.assertRaises(TacticDenied):
            run(registry, "soft")

    def test_exception_is_isolated(self):
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="boom", summary="b"),
                                 lambda ctx: 1 / 0))
        with self.assertRaises(TacticFailed):
            run(registry, "boom")

    def test_intent_budget(self):
        registry = self._registry(max_intents=2)
        registry.register(Tactic(TacticInfo(name="many", summary="m"),
                                 lambda ctx: tuple(range(3))))
        with self.assertRaises(TacticError) as ctx:
            run(registry, "many")
        self.assertIn("上限", str(ctx.exception))

    def test_unknown_condition_is_rejected(self):
        registry = self._registry()
        registry.register(Tactic(TacticInfo(name="x", summary="x",
                                            requires=("nope",)),
                                 lambda ctx: ()))
        with self.assertRaises(TacticError):
            run(registry, "x")


# ---------------------------------------------------------------- 上下文
class TestContext(unittest.TestCase):
    def test_intent_fills_envelope(self):
        built = {}

        def build(ctx):
            built["intent"] = ctx.intent(MoveTo, units=(1,), cell=(3, 4))
            return ()

        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="b", summary="b"), build))
        run(registry, "b", subject=FakeSubject(agents=(7, 8)), frame=55)
        intent = built["intent"]
        self.assertEqual(intent.layer, Layer.L1_TACTIC)
        self.assertEqual(intent.created_frame, 55)
        self.assertEqual(intent.scope, Scope(objects=(7, 8)))

    def test_intent_scope_can_be_narrowed(self):
        built = {}

        def build(ctx):
            built["intent"] = ctx.intent(Hold, units=(7,), scope=(7,))
            return ()

        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="b", summary="b"), build))
        run(registry, "b", subject=FakeSubject(agents=(7, 8)))
        self.assertEqual(built["intent"].scope, Scope(objects=(7,)))

    def test_memo_is_isolated_per_tactic(self):
        # 技法之间不共享记事本：要传东西就显式走参数或组合调用
        def first(ctx):
            ctx.remember("origin", (1, 2))
            return ()

        def second(ctx):
            ctx.remember("seen", ctx.recall("origin"))
            return ()

        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="a", summary="a"), first))
        registry.register(Tactic(TacticInfo(name="b", summary="b"), second))
        memo = {}
        registry.run("a", observation=make_observation(), subject=FakeSubject(),
                     params={}, frame=1, memo=memo)
        registry.run("b", observation=make_observation(), subject=FakeSubject(),
                     params={}, frame=2, memo=memo)
        self.assertEqual(memo[("a", "origin")], (1, 2))
        self.assertIsNone(memo[("b", "seen")])

    def test_attempt_is_visible(self):
        seen = {}

        def build(ctx):
            seen["attempt"] = ctx.attempt
            return ()

        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="a", summary="a"), build))
        run(registry, "a", attempt=2)
        self.assertEqual(seen["attempt"], 2)


# ---------------------------------------------------------------- 策略
class TestPolicy(unittest.TestCase):
    def test_round_trip(self):
        policy = TacticPolicy(max_level={Layer.L1_TACTIC: Level.EDGE},
                              enabled=frozenset({"a"}), disabled=frozenset({"b"}),
                              max_depth=4, max_intents=9)
        restored = TacticPolicy.from_dict(json.loads(json.dumps(policy.to_dict())))
        self.assertEqual(restored.max_depth, 4)
        self.assertEqual(restored.max_intents, 9)
        self.assertEqual(restored.max_level[Layer.L1_TACTIC], Level.EDGE)
        self.assertEqual(restored.enabled, frozenset({"a"}))
        self.assertEqual(restored.disabled, frozenset({"b"}))

    def test_unknown_field_is_rejected(self):
        with self.assertRaises(TacticError):
            TacticPolicy.from_dict({"max_depth": 1, "typo": 2})

    def test_missing_file_gives_defaults(self):
        policy = TacticPolicy.load("/nonexistent/tactics.json")
        self.assertEqual(policy.max_depth, TacticPolicy().max_depth)

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "p.json")
            TacticPolicy(max_intents=7).save(path)
            self.assertEqual(TacticPolicy.load(path).max_intents, 7)

    def test_malformed_file_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "p.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{ not json")
            with self.assertRaises(json.JSONDecodeError):
                TacticPolicy.load(path)

    def test_level_gate_defaults_to_normal(self):
        policy = TacticPolicy()
        self.assertTrue(policy.allows(TacticInfo(name="a", summary="a")))
        self.assertFalse(policy.allows(TacticInfo(name="a", summary="a",
                                                  level=Level.EDGE)))


class TestFingerprint(unittest.TestCase):
    def test_stable_for_the_same_library(self):
        self.assertEqual(TacticRegistry().load_builtin().fingerprint(),
                         TacticRegistry().load_builtin().fingerprint())

    def test_changes_with_the_library(self):
        registry = TacticRegistry()
        registry.register(Tactic(TacticInfo(name="a", summary="a", version=1),
                                 lambda ctx: ()))
        before = registry.fingerprint()
        registry.register(Tactic(TacticInfo(name="b", summary="b", version=1),
                                 lambda ctx: ()))
        self.assertNotEqual(before, registry.fingerprint())


if __name__ == "__main__":
    unittest.main()


class TestContextTypes(unittest.TestCase):
    """技法靠 `ctx.types` 把类型名解析成指针——`Produce` 一类意图需要它。"""

    def context(self, types=None):
        from ra2agent.observation import Observation
        from ra2agent.state import GameState
        from tests.fixtures import build_game_state, build_house
        state = GameState.parse(build_game_state(
            houses=[build_house(0x1000, current_player=True)]))
        observation = Observation(frame=state.frame, house=state.player_house(),
                                  state=state, types=types)
        return TacticContext(registry=None, tactic=None, observation=observation,
                             subject=None, params={}, frame=state.frame, memo={},
                             log=None, chain=(), attempt=0, budget=None)

    def table(self, aliases=None):
        from ra2agent.state import ObjectType, TypeTable
        return TypeTable([ObjectType(name="Grizzly Battle Tank", cost=700,
                                     array_index=1, pointer=0x900, type=1)],
                         aliases=aliases)

    def test_types_is_reachable(self):
        self.assertIsNotNone(self.context(self.table()).types)

    def test_no_table_is_tolerated(self):
        self.assertIsNone(self.context(None).types)
        self.assertIsNone(self.context(None).type_pointer("MTNK"))

    def test_resolves_by_display_name(self):
        self.assertEqual(self.context(self.table()).type_pointer("Grizzly Battle Tank"), 0x900)

    def test_resolves_by_registered_name_when_aliased(self):
        context = self.context(self.table(aliases={"MTNK": 0x900}))
        self.assertEqual(context.type_pointer("MTNK"), 0x900)

    def test_unknown_name_gives_none(self):
        # 技法应当据此放弃，而不是拿个假指针去下单
        self.assertIsNone(self.context(self.table()).type_pointer("Nonexistent"))
