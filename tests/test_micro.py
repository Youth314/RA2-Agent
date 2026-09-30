"""L1 运行时的测试。

覆盖：编队建立、到位判定、卡住换路点、接战与脱战、对象消失、以及四类命令异常
的处置。执行器是假的，不碰游戏，也不需要真技法——技法库用内置的。
"""
import unittest

from ra2agent.client import CommandResult
from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.errors import (CommandFailed, GameNotResponding, InvalidCommand,
                             TacticError, Timeout)
from ra2agent.executor import CommandPlan, ExecutionOutcome
from ra2agent.identity import IdentityTable
from ra2agent.intents import IntentState, Scope, TacticCall
from ra2agent.micro import MicroLayer, UnitMode
from ra2agent.observation import Observation
from ra2agent.state import GameState, MapData
from ra2agent.tactics import TacticRegistry
from tests.fixtures import (ENEMY_HOUSE, PLAYER_HOUSE, build_game_state,
                            build_house, build_map_soa, build_object)

SIDE = 9
ALLY_A = 0xA1
ALLY_B = 0xA2
ENEMY = 0xB1
ENEMY_B = 0xB2


# ---------------------------------------------------------------- 构造
def make_map():
    cells = SIDE * SIDE
    return MapData.parse(build_map_soa(width=SIDE, height=SIDE,
                                       shrouded=[0] * cells,
                                       land=[LandType.CLEAR] * cells))


def at(cell):
    return cell[0] * 256 + 128, cell[1] * 256 + 128


def make_state(frame=100, objects=()):
    return GameState.parse(build_game_state(
        frame=frame,
        houses=[build_house(PLAYER_HOUSE, current_player=True),
                build_house(ENEMY_HOUSE)],
        objects=list(objects)))


def tank(pointer, cell, house=PLAYER_HOUSE, mission=Mission.GUARD, **kwargs):
    x, y = at(cell)
    return build_object(pointer, house=house, object_type=AbstractType.UNIT,
                        mission=mission, x=x, y=y, **kwargs)


def make_observation(state, map_data=None, enemies=()):
    return Observation(frame=state.frame, house=state.player_house(),
                       own=tuple(o for o in state.objects
                                 if o.house == PLAYER_HOUSE),
                       visible_enemies=tuple(enemies), neutral=(),
                       state=state, map_data=map_data if map_data else MAP)


MAP = make_map()


class FakeExecutor:
    """记录意图的假执行器。`errors` 逐次弹出，用完后回落到 `error`。"""

    def __init__(self, error=None, errors=()):
        self.calls = []
        self.error = error
        self._errors = list(errors)

    def execute(self, intent, state):
        self.calls.append(intent)
        error = self._errors.pop(0) if self._errors else self.error
        if error is not None:
            raise error
        plan = CommandPlan(kind=intent.kind, command="UnitOrder", action=None,
                           verify=lambda current: True)
        return ExecutionOutcome(
            intent_id=intent.id, kind=intent.kind, plan=plan, frames_waited=0,
            polls=1, state=state,
            result=CommandResult(type="UnitOrder", payload=b"", code=None, error=""))


class FakeObserver:
    """最小观测源：标识表、地图、类型表。"""

    def __init__(self, state, map_data=None):
        self.identity = IdentityTable()
        self.identity.update(state)
        self.map_data = map_data if map_data else MAP
        self.types = None
        self.client = None


class Case(unittest.TestCase):
    """搭好观测源、假执行器与运行时。"""

    def build(self, state, executor=None, **kwargs):
        self.observer = FakeObserver(state)
        self.executor = executor or FakeExecutor()
        kwargs.setdefault("sleep", lambda _: None)
        self.layer = MicroLayer(self.observer, TacticRegistry().load_builtin(),
                                self.executor, **kwargs)
        return self.layer

    def agent(self, pointer):
        """对象指针的 Agent 侧 id。"""
        return self.observer.identity.agent_id(pointer)

    def assign(self, state, tactic, params=None, agents=(1,)):
        call = TacticCall(tactic=tactic, params=params or {},
                          scope=Scope(objects=tuple(agents)))
        return self.layer.assign(call, make_observation(state)), call

    def tick(self, state, enemies=()):
        return self.layer.tick(make_observation(state, enemies=enemies))


# ---------------------------------------------------------------- 建队
class TestAssign(Case):
    def test_squad_is_created(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, _ = self.assign(state, "hold_position")
        self.assertEqual(len(squad.units), 1)
        self.assertEqual(squad.units[0].mode, UnitMode.MOVING)

    def test_unknown_objects_are_skipped(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, _ = self.assign(state, "hold_position",
                               agents=(self.agent(ALLY_A), 9999))
        self.assertEqual(len(squad.units), 1)

    def test_no_valid_object_is_an_error(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        with self.assertRaises(TacticError):
            call = TacticCall(tactic="hold_position", scope=Scope(objects=(0xDEAD,)))
            self.layer.assign(call, make_observation(state))

    def test_unknown_tactic_is_an_error(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        with self.assertRaises(TacticError):
            self.assign(state, "no_such_tactic")

    def test_only_command_intents_are_accepted(self):
        from ra2agent.intents import Hold
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        with self.assertRaises(TacticError):
            self.layer.assign(Hold(units=(1,)), make_observation(state))


# ---------------------------------------------------------------- 驻守
class TestHold(Case):
    def test_stop_then_settle_satisfied(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "hold_position")
        self.tick(state)
        self.assertEqual([i.kind for i in self.executor.calls], ["hold"])
        self.assertEqual(squad.units[0].mode, UnitMode.ARRIVED)
        self.assertEqual(squad.units[0].goal, None)
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(call.state, IntentState.SATISFIED)
        self.assertEqual(self.layer.completed[0]["state"], "satisfied")

    def test_one_command_covers_the_whole_squad(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)), tank(ALLY_B, (2, 2))])
        self.build(state)
        first, second = self.agent(ALLY_A), self.agent(ALLY_B)
        self.assign(state, "hold_position", agents=(first, second))
        self.tick(state)
        self.assertEqual(len(self.executor.calls), 1)
        self.assertEqual(self.executor.calls[0].units, (first, second))


# ---------------------------------------------------------------- 推进
class TestAdvance(Case):
    def test_one_move_order_per_unit(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)), tank(ALLY_B, (1, 2))])
        self.build(state)
        squad, _ = self.assign(state, "advance_to_cell", {"cell": (5, 5)},
                               agents=(self.agent(ALLY_A), self.agent(ALLY_B)))
        self.tick(state)
        self.assertEqual([i.kind for i in self.executor.calls], ["move_to", "move_to"])
        goals = [unit.goal for unit in squad.units]
        self.assertEqual(len(set(goals)), 2)                  # 队形摊开，不挤一格
        self.assertTrue(all(max(abs(g[0] - 5), abs(g[1] - 5)) <= 4 for g in goals))

    def test_no_repeat_while_under_way(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        self.tick(state)
        self.assertEqual(len(self.executor.calls), 1)

    def test_arrival_settles(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        goal = squad.units[0].goal
        arrived = make_state(frame=130, objects=[tank(ALLY_A, goal)])
        self.tick(arrived)
        self.assertEqual(squad.units[0].mode, UnitMode.ARRIVED)
        self.assertEqual(call.state, IntentState.SATISFIED)

    def test_arrival_allows_one_cell_slack(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, _ = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        goal = squad.units[0].goal
        neighbour = (goal[0] + 1, goal[1])
        self.tick(make_state(frame=130, objects=[tank(ALLY_A, neighbour)]))
        self.assertEqual(squad.units[0].mode, UnitMode.ARRIVED)


# ---------------------------------------------------------------- 卡住
class TestStuck(Case):
    def test_stuck_reorders_with_a_different_cell(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state, stuck_frames=50)
        squad, _ = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        first_goal = squad.units[0].goal
        self.assertEqual(len(self.executor.calls), 1)
        # 位置不动超过 stuck_frames：同一拍就换一个落点重新下令
        later = make_state(frame=200, objects=[tank(ALLY_A, (1, 1))])
        self.tick(later)
        self.assertEqual(len(self.executor.calls), 2)
        self.assertEqual(squad.units[0].retries, 1)
        self.assertNotEqual(squad.units[0].goal, first_goal)
        self.assertEqual(squad.units[0].mode, UnitMode.MOVING)

    def test_stuck_too_often_fails(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state, stuck_frames=50, max_retries=2)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        for frame in (100, 200, 300, 400):
            self.tick(make_state(frame=frame, objects=[tank(ALLY_A, (1, 1))]))
        self.assertEqual(squad.units[0].mode, UnitMode.FAILED)
        self.assertEqual(call.state, IntentState.FAILED)
        self.assertEqual(self.layer.completed[0]["state"], "failed")


# ---------------------------------------------------------------- 接战
class TestEngage(Case):
    def test_advance_covering_engages_when_enemy_visible(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        squad, _ = self.assign(state, "advance_covering",
                               {"cell": (5, 5), "radius": 8})
        self.tick(state, enemies=[enemy])
        self.assertEqual([i.kind for i in self.executor.calls], ["attack"])
        self.assertEqual(squad.units[0].mode, UnitMode.ENGAGING)

    def test_advance_covering_advances_when_clear(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        self.assign(state, "advance_covering", {"cell": (5, 5)})
        self.tick(state)
        self.assertEqual([i.kind for i in self.executor.calls], ["move_to"])

    def test_contact_over_resumes_the_advance(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        squad, _ = self.assign(state, "advance_covering",
                               {"cell": (5, 5), "radius": 8})
        self.tick(state, enemies=[enemy])
        # 敌人消失后回到推进，而不是停在原地
        clear = make_state(frame=140, objects=[tank(ALLY_A, (1, 1))])
        self.tick(clear)
        self.assertEqual(squad.units[0].mode, UnitMode.MOVING)
        self.assertEqual(self.executor.calls[-1].kind, "move_to")

    def test_enemy_out_of_radius_is_ignored(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (8, 8), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        self.assign(state, "engage_nearest", {"radius": 2})
        self.tick(state, enemies=[enemy])
        self.assertEqual(self.executor.calls, [])


# ---------------------------------------------------------------- 停止开火
class TestHoldAndFire(Case):
    def test_enemy_in_range_fires_instead_of_halting(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        squad, _ = self.assign(state, "hold_and_fire", {"radius": 8})
        self.tick(state, enemies=[enemy])
        self.assertEqual([i.kind for i in self.executor.calls], ["attack"])
        self.assertEqual(squad.units[0].mode, UnitMode.ENGAGING)

    def test_nearest_enemy_is_targeted(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE),
                                    tank(ENEMY_B, (2, 2), house=ENEMY_HOUSE)])
        far, near = state.object(ENEMY), state.object(ENEMY_B)
        self.build(state)
        self.assign(state, "hold_and_fire", {"radius": 8})
        self.tick(state, enemies=[far, near])
        self.assertEqual(self.executor.calls[0].kind, "attack")
        self.assertEqual(self.executor.calls[0].target, self.agent(ENEMY_B))

    def test_only_units_with_a_target_fire(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)), tank(ALLY_B, (7, 7)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        first, second = self.agent(ALLY_A), self.agent(ALLY_B)
        squad, _ = self.assign(state, "hold_and_fire", {"radius": 3},
                               agents=(first, second))
        self.tick(state, enemies=[enemy])
        self.assertEqual([i.kind for i in self.executor.calls], ["attack", "hold"])
        modes = {unit.agent_id: unit.mode for unit in squad.units}
        self.assertEqual(modes[first], UnitMode.ENGAGING)
        self.assertEqual(modes[second], UnitMode.ARRIVED)

    def test_enemy_out_of_radius_halts_and_settles(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (8, 8), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        _, call = self.assign(state, "hold_and_fire", {"radius": 2})
        self.tick(state, enemies=[enemy])
        self.assertEqual([i.kind for i in self.executor.calls], ["hold"])
        self.assertEqual(call.state, IntentState.SATISFIED)

    def test_target_lost_halts_and_settles(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)),
                                    tank(ENEMY, (3, 3), house=ENEMY_HOUSE)])
        enemy = state.object(ENEMY)
        self.build(state)
        squad, call = self.assign(state, "hold_and_fire", {"radius": 8})
        self.tick(state, enemies=[enemy])
        self.assertEqual(squad.units[0].mode, UnitMode.ENGAGING)
        clear = make_state(frame=140, objects=[tank(ALLY_A, (1, 1))])
        self.tick(clear)
        self.assertEqual(self.executor.calls[-1].kind, "hold")
        self.assertEqual(squad.units[0].mode, UnitMode.ARRIVED)
        self.assertEqual(call.state, IntentState.SATISFIED)


# ---------------------------------------------------------------- 损失
class TestLosses(Case):
    def test_vanished_unit_is_lost(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        self.tick(make_state(frame=120, objects=[]))
        self.assertEqual(squad.units[0].mode, UnitMode.LOST)
        self.assertEqual(call.state, IntentState.FAILED)

    def test_partial_loss_still_satisfies(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1)), tank(ALLY_B, (2, 2))])
        self.build(state)
        first, second = self.agent(ALLY_A), self.agent(ALLY_B)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)},
                                  agents=(first, second))
        self.tick(state)
        goals = {unit.agent_id: unit.goal for unit in squad.units}
        survivor = make_state(frame=140,
                              objects=[tank(ALLY_A, goals[first])])
        self.tick(survivor)
        self.assertEqual(call.state, IntentState.SATISFIED)
        record = self.layer.completed[0]
        self.assertEqual(record["lost"], [second])
        self.assertEqual(record["arrived"], [first])


# ---------------------------------------------------------------- 异常
class TestCommandErrors(Case):
    def test_missing_object_fails_the_unit(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        executor = FakeExecutor(error=CommandFailed("gone", reason="object_missing"))
        self.build(state, executor=executor)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        self.assertEqual(squad.units[0].mode, UnitMode.FAILED)
        self.assertEqual(call.state, IntentState.FAILED)

    def test_timeout_retries_then_fails(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        executor = FakeExecutor(error=Timeout("no effect"))
        self.build(state, executor=executor, max_retries=2)
        squad, _ = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        for _ in range(4):
            self.tick(state)
        self.assertEqual(len(executor.calls), 3)          # 首次加两次重试
        self.assertEqual(squad.units[0].mode, UnitMode.FAILED)

    def test_lost_focus_pauses_without_failing(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        executor = FakeExecutor(error=GameNotResponding("paused"))
        self.build(state, executor=executor)
        squad, _ = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        self.assertEqual(squad.units[0].mode, UnitMode.MOVING)
        self.assertEqual(squad.units[0].goal, None)
        self.assertEqual(squad.units[0].retries, 0)
        self.assertEqual(self.layer.squads(), (squad,))

    def test_invalid_command_fails_the_squad(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        executor = FakeExecutor(error=InvalidCommand("越界"))
        self.build(state, executor=executor)
        _, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        self.assertEqual(call.state, IntentState.FAILED)

    def test_other_server_errors_fail_the_squad(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        executor = FakeExecutor(error=CommandFailed("blocked", reason="unbuildable"))
        self.build(state, executor=executor)
        _, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        self.tick(state)
        self.assertEqual(call.state, IntentState.FAILED)


# ---------------------------------------------------------------- 期限
class TestExpiry(Case):
    def test_expired_intent_settles(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        call.created_frame = 100
        call.ttl_frames = 10
        self.tick(make_state(frame=200, objects=[tank(ALLY_A, (1, 1))]))
        self.assertEqual(call.state, IntentState.EXPIRED)
        self.assertEqual(self.layer.completed[0]["state"], "expired")

    def test_live_intent_is_not_expired(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        call.created_frame = 100
        call.ttl_frames = 500
        self.tick(state)
        self.assertEqual(self.layer.squads(), (squad,))


class TestIdleAndWaiting(Case):
    """「技法这一拍不产意图」的两种语义，以及等待的上限与告警限频。

    以前两种都只会挂住：任务不结算、单位被占死，而每拍还发一条同样的告警
    （实测 `deploy_mcv` 挂过两千多帧、单次 `status` 堆过 20 条「等待」）。
    """

    def test_idle_ends_task_settles_and_releases_the_unit(self):
        """标了 `idle_ends_task` 的技法：没事可做就当场收工交还单位。"""
        state = make_state(objects=[tank(ALLY_A, (1, 1))])   # 一辆坦克，不是基地车
        self.build(state)
        squad, call = self.assign(state, "deploy_mcv")
        self.tick(state)
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(call.state, IntentState.IDLE)
        self.assertEqual(self.layer.completed[0]["state"], "idle")
        self.assertIn("无事可做", self.layer.completed[0]["reason"])
        # 单位交还：它不再属于任何在管任务
        self.assertEqual(self.layer.progress(), ())

    def test_conditions_unmet_waits_instead_of_settling(self):
        """条件不满足是「等局面变化」，不是「没事可做」——不该当场收工。"""
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "engage_nearest", {"radius": 8})
        self.tick(state)                       # 场上没有敌人
        self.assertEqual(self.layer.squads(), (squad,))
        self.assertEqual(call.state, IntentState.ACTIVE)

    def test_waiting_notice_is_throttled(self):
        """同类等待告警按帧限频，不能每拍一条。"""
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        self.assign(state, "engage_nearest", {"radius": 8})
        for frame in range(100, 400, 11):      # 二十多拍
            self.tick(make_state(frame=frame, objects=[tank(ALLY_A, (1, 1))]))
        self.assertEqual(len(self.layer.notices), 1)

    def test_waiting_for_too_long_settles_with_a_reason(self):
        """等太久就收工：单位不能被一条任务永久占着。"""
        from ra2agent.micro import WAIT_GRACE_FRAMES
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "engage_nearest", {"radius": 8})
        self.tick(state)
        self.tick(make_state(frame=100 + WAIT_GRACE_FRAMES,
                             objects=[tank(ALLY_A, (1, 1))]))
        self.assertEqual(self.layer.squads(), ())
        self.assertEqual(call.state, IntentState.FAILED)
        self.assertIn("局面没变", self.layer.completed[0]["reason"])

    def test_a_wait_that_keeps_changing_its_reason_is_not_reaped(self):
        """等待的理由一变就重新计时：正在等的前提不该被当成死等清掉。

        `place_ready_building` 抢跑是等 `has_pending_building`，而这条理由在
        「还没开始造」与「造好了待放」之间会变——故只有同一个理由连续超时才收。
        """
        from ra2agent.micro import WAIT_GRACE_FRAMES
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, call = self.assign(state, "engage_nearest", {"radius": 8})
        self.tick(state)
        self.assertEqual(self.layer.squads(), (squad,))
        # 还没到上限：仍在等
        self.tick(make_state(frame=100 + WAIT_GRACE_FRAMES - 1,
                             objects=[tank(ALLY_A, (1, 1))]))
        self.assertEqual(self.layer.squads(), (squad,))


class TestCards(Case):
    def test_cards_reflect_the_situation(self):
        state = make_state(objects=[tank(ALLY_A, (1, 1))])
        self.build(state)
        squad, _ = self.assign(state, "advance_to_cell", {"cell": (5, 5)})
        names = [card.name for card in
                 self.layer.cards(make_observation(state), squad)]
        self.assertIn("advance_to_cell", names)
        self.assertNotIn("engage_nearest", names)


if __name__ == "__main__":
    unittest.main()
