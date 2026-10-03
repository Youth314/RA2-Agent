"""事件合成的测试。

关键是**纯函数**：同样的前后两帧必须给出同样的事件。回放场景存的是原始帧，
离线闭环要靠它重新合成事件来验证「事件触发的技法」。
"""
import unittest

from ra2agent.engine.events import (MAX_LISTED_PER_KIND, Event, EventKind, EventLog,
                             Policy, Subject, detect, summarize)
from ra2agent.engine.observation import Observation
from ra2agent.engine.state import GameState
from tests.fixtures import (ENEMY_HOUSE, NEUTRAL_HOUSE, PLAYER_HOUSE,
                            build_factory, build_game_state, build_house)


def frame(houses, frame_number=100):
    """一帧观测。第一个阵营当己方。"""
    state = GameState.parse(build_game_state(houses=list(houses), frame=frame_number))
    return Observation(frame=state.frame, house=state.player_house(), state=state)


def me(**kwargs):
    """己方阵营，默认一个玩家。"""
    return build_house(PLAYER_HOUSE, current_player=True, **kwargs)


def other(**kwargs):
    return build_house(ENEMY_HOUSE, **kwargs)


class TestObjectLoss(unittest.TestCase):
    """己方对象从地图上消失 = 掉单位/掉建筑。

    这是玩家 agent 报出的能力缺口：单位 id 会凭空消失，`status` 只说「这些 id 不是
    你方可用单位」，分不出是损失了还是观测换了。
    """

    def _frame(self, objects, number=100, own=None):
        state = GameState.parse(build_game_state(
            houses=[me()], objects=list(objects), frame=number))
        # `build_object` 给的是线上字节，`GameState.parse` 之后才是对象；`own`
        # 装的是解析后的对象（跟真实观测一致）。
        mine = state.objects if own is None else own
        return Observation(frame=state.frame, house=state.player_house(),
                           own=tuple(mine), state=state)

    def _tank(self, pointer=0xB1, in_limbo=False):
        from ra2agent.constants import AbstractType, Mission
        from tests.fixtures import build_object
        return build_object(pointer, house=PLAYER_HOUSE,
                            object_type=AbstractType.UNIT, mission=Mission.GUARD,
                            x=300, y=300, in_limbo=in_limbo, on_map=not in_limbo)

    def test_a_vanished_object_is_reported(self):
        before = self._frame([self._tank()])
        after = self._frame([])
        events = [e for e in detect(before, after)
                  if e.kind is EventKind.OBJECT_LOST]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].data["count"], 1)
        self.assertIn("损失", events[0].render())

    def test_a_completed_building_entering_limbo_is_not_a_loss(self):
        """完工待放置：从 `own` 里消失，但指针还在——那是去放置，不是被打掉。"""
        before = self._frame([self._tank()])
        after = self._frame([self._tank(in_limbo=True)], own=())
        self.assertEqual(
            [e for e in detect(before, after)
             if e.kind is EventKind.OBJECT_LOST], [])

    def test_nothing_lost_reports_nothing(self):
        before = self._frame([self._tank()])
        after = self._frame([self._tank()], number=110)
        self.assertEqual(
            [e for e in detect(before, after)
             if e.kind is EventKind.OBJECT_LOST], [])


class TestPlacementReady(unittest.TestCase):
    """新出现一栋完工待放置的建筑时报一次——放哪儿是模型的事，得把它叫回来。"""

    def _frame(self, objects, number=100, factories=()):
        state = GameState.parse(build_game_state(
            houses=[me()], objects=list(objects), frame=number,
            factories=factories))
        return Observation(frame=state.frame, house=state.player_house(),
                           own=tuple(state.objects), state=state)

    def _building(self, pointer=0xC1, in_limbo=False):
        from ra2agent.constants import AbstractType, Mission
        from tests.fixtures import build_object
        return build_object(pointer, house=PLAYER_HOUSE,
                            object_type=AbstractType.BUILDING,
                            mission=Mission.CONSTRUCTION, x=300, y=300,
                            in_limbo=in_limbo, on_map=not in_limbo)

    def test_completion_while_already_in_limbo_reports_once(self):
        before = self._frame([self._building(in_limbo=True)],
                             factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=53)])
        after = self._frame([self._building(in_limbo=True)], number=110,
                            factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=54)])
        ready = [e for e in detect(before, after)
                 if e.kind is EventKind.PLACEMENT_READY]
        self.assertEqual(len(ready), 1)
        self.assertIn("完工待放置", ready[0].render())

    def test_staying_in_limbo_does_not_report_again(self):
        factories = [build_factory(PLAYER_HOUSE, 0xC1, timer=54)]
        before = self._frame([self._building(in_limbo=True)], factories=factories)
        after = self._frame([self._building(in_limbo=True)], number=120, factories=factories)
        self.assertEqual(
            [e for e in detect(before, after)
             if e.kind is EventKind.PLACEMENT_READY], [])

    def test_a_unit_rolling_out_of_a_factory_is_not_reported(self):
        """出厂的单位也会短暂进 limbo，但「放哪儿」只对建筑成立——别为它叫模型。"""
        from ra2agent.constants import AbstractType, Mission
        from tests.fixtures import build_object
        unit = build_object(0xE1, house=PLAYER_HOUSE, object_type=AbstractType.UNIT,
                            mission=Mission.GUARD, x=300, y=300, in_limbo=True,
                            on_map=False)
        before = self._frame([])
        after = self._frame([unit], number=140,
                            factories=[build_factory(PLAYER_HOUSE, 0xE1, timer=54)])
        self.assertEqual(
            [e for e in detect(before, after)
             if e.kind is EventKind.PLACEMENT_READY], [])

    def test_a_placed_building_is_not_reported(self):
        before = self._frame([self._building()])
        after = self._frame([self._building()], number=130,
                            factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=54)])
        self.assertEqual(
            [e for e in detect(before, after)
             if e.kind is EventKind.PLACEMENT_READY], [])

    def test_production_pause_completion_and_placement_event_cycle(self):
        log = EventLog()
        log.update(self._frame([]))
        for number, timer, held in ((101, 0, False), (102, 25, True), (103, 53, False)):
            events = log.update(self._frame([self._building(in_limbo=True)], number,
                factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=timer, on_hold=held)]))
            self.assertEqual(events, ())
        ready = self._frame([self._building(in_limbo=True)], 104,
                            factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=54)])
        self.assertEqual([e.kind for e in log.update(ready)], [EventKind.PLACEMENT_READY])
        self.assertEqual(log.update(ready), ())
        self.assertEqual(log.update(self._frame([self._building(in_limbo=True)], 105,
            factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=54)])), ())
        self.assertEqual(log.update(self._frame([self._building()], 106,
            factories=[build_factory(PLAYER_HOUSE, 0xC1, timer=54)])), ())
        self.assertEqual(len(log), 1)

    def test_reused_pointer_with_new_native_identity_is_a_new_ready_building(self):
        from ra2agent.engine.proto import pb_uint
        factories = [build_factory(PLAYER_HOUSE, 0xC1, timer=54)]
        before = self._frame([self._building(in_limbo=True) + pb_uint(21, 100)],
                             factories=factories)
        after = self._frame([self._building(in_limbo=True) + pb_uint(21, 101)],
                            number=110, factories=factories)
        self.assertEqual([e.kind for e in detect(before, after)], [EventKind.PLACEMENT_READY])


class TestPureFunction(unittest.TestCase):
    def test_first_frame_reports_nothing(self):
        # 第一帧没有「之前」，当前局面由本局简报负责，那不是事件
        self.assertEqual(detect(None, frame([me()])), ())

    def test_same_inputs_give_the_same_events(self):
        before = frame([me(power_output=200, power_drain=50)])
        after = frame([me(power_output=100, power_drain=150)])
        self.assertEqual(detect(before, after), detect(before, after))

    def test_no_change_reports_nothing(self):
        one = frame([me(power_output=100, power_drain=150)])
        two = frame([me(power_output=100, power_drain=150)])
        self.assertEqual(detect(one, two), ())


class TestLowPower(unittest.TestCase):
    def test_onset_is_reported_once(self):
        enough = frame([me(power_output=200, power_drain=50)])
        short = frame([me(power_output=100, power_drain=150)])
        events = detect(enough, short)
        self.assertEqual([e.kind for e in events], [EventKind.LOW_POWER])
        self.assertEqual(events[0].data["output"], 100)
        self.assertEqual(events[0].data["drain"], 150)

    def test_staying_short_is_not_repeated(self):
        short = [me(power_output=100, power_drain=150)]
        self.assertEqual(detect(frame(short), frame(short)), ())

    def test_recovery_is_not_reported(self):
        # 恢复让模型自己看状态——事件是用来打断的，不是用来记流水账的
        short = frame([me(power_output=100, power_drain=150)])
        enough = frame([me(power_output=200, power_drain=50)])
        self.assertEqual(detect(short, enough), ())

    def test_equal_is_not_short(self):
        one = frame([me(power_output=100, power_drain=100)])
        two = frame([me(power_output=100, power_drain=100)])
        self.assertEqual(detect(one, two), ())


class TestInsufficientFunds(unittest.TestCase):
    def test_crossing_the_threshold_is_reported(self):
        events = detect(frame([me(money=500)]), frame([me(money=100)]))
        self.assertIn(EventKind.INSUFFICIENT_FUNDS, [e.kind for e in events])

    def test_already_below_is_not_repeated(self):
        low = [me(money=100)]
        self.assertEqual(detect(frame(low), frame(low)), ())

    def test_threshold_is_configurable(self):
        before, after = frame([me(money=500)]), frame([me(money=400)])
        self.assertEqual(detect(before, after), ())
        self.assertTrue(detect(before, after, Policy(funds_threshold=450)))

    def test_going_up_does_not_report(self):
        self.assertEqual(detect(frame([me(money=100)]), frame([me(money=500)])), ())


class TestInfiltration(unittest.TestCase):
    def test_each_side_is_reported(self):
        for side in ("allied", "soviet", "third"):
            with self.subTest(side=side):
                events = detect(frame([me()]), frame([me(infiltrated=(side,))]))
                self.assertEqual([e.kind for e in events], [EventKind.INFILTRATED])
                self.assertEqual(events[0].data["side"], side)

    def test_all_three_at_once(self):
        events = detect(frame([me()]), frame([me(infiltrated=("allied", "soviet", "third"))]))
        self.assertEqual(len(events), 3)

    def test_staying_infiltrated_is_not_repeated(self):
        one = frame([me(infiltrated=("soviet",))])
        self.assertEqual(detect(one, one), ())

    def test_side_labels_are_chinese(self):
        events = detect(frame([me()]), frame([me(infiltrated=("third",))]))
        self.assertIn("尤里", events[0].render())


class TestPlayerDefeated(unittest.TestCase):
    def test_defeat_is_reported_with_its_subject(self):
        before = frame([me(), other()])
        after = frame([me(), other(defeated=True)])
        events = detect(before, after)
        self.assertEqual([e.kind for e in events], [EventKind.PLAYER_DEFEATED])
        self.assertEqual(events[0].subject.is_human, False, "电脑玩家")
        self.assertFalse(events[0].subject.is_you)

    def test_the_local_player_is_marked(self):
        before = frame([me(), other()])
        after = frame([me(defeated=True), other()])
        self.assertTrue(detect(before, after)[0].subject.is_you)

    def test_already_defeated_is_not_repeated(self):
        one = frame([me(), other(defeated=True)])
        self.assertEqual(detect(one, one), ())

    def test_neutral_houses_are_not_players(self):
        before = frame([me(), build_house(NEUTRAL_HOUSE, faction="Neutral")])
        after = frame([me(), build_house(NEUTRAL_HOUSE, faction="Neutral", defeated=True)])
        self.assertEqual(detect(before, after), ())

    def test_subject_renders_readably(self):
        before = frame([me(), other()])
        after = frame([me(), other(defeated=True)])
        self.assertIn("电脑", detect(before, after)[0].render())


class TestFogDiscipline(unittest.TestCase):
    """只用己方状态与公开信息，不读敌方的内部状态。"""

    def test_enemy_power_change_is_not_an_event(self):
        before = frame([me(), other(power_output=200, power_drain=0)])
        after = frame([me(), other(power_output=0, power_drain=300)])
        self.assertEqual(detect(before, after), ())

    def test_enemy_infiltration_is_not_an_event(self):
        # 敌方的渗透标志是它的内部状态
        before = frame([me(), other()])
        after = frame([me(), other(infiltrated=("allied", "soviet", "third"))])
        self.assertEqual(detect(before, after), ())

    def test_enemy_money_change_is_not_an_event(self):
        before = frame([me(), other(money=10000)])
        after = frame([me(), other(money=0)])
        self.assertEqual(detect(before, after), ())


if __name__ == "__main__":
    unittest.main()


class TestEventLog(unittest.TestCase):
    def log_with(self, events, capacity=256):
        log = EventLog(capacity=capacity)
        log.record(events)
        return log

    def make(self, kind, frame=1, name="me", **data):
        return Event(kind=kind, frame=frame, subject=Subject("house", 0, name), data=data)

    def test_feeding_the_same_frame_twice_reports_once(self):
        # tick() 与 status() 都可能触发读帧，靠这条保证不重复
        log = EventLog()
        one = frame([me()])
        self.assertEqual(log.update(one), ())
        log.update(one)
        self.assertEqual(len(log), 0)

    def test_a_new_frame_is_detected(self):
        log = EventLog()
        log.update(frame([me(money=500)]))
        events = log.update(frame([me(money=100)], frame_number=101))
        self.assertEqual([e.kind for e in events], [EventKind.INSUFFICIENT_FUNDS])

    def test_first_frame_reports_nothing(self):
        self.assertEqual(EventLog().update(frame([me()])), ())

    def test_cursor_returns_only_what_is_new(self):
        log = self.log_with([self.make(EventKind.LOW_POWER, frame=i) for i in range(3)])
        events, cursor = log.new_since(1)
        self.assertEqual(len(events), 2)
        self.assertEqual(cursor, 3)
        self.assertEqual(log.new_since(cursor)[0], ())

    def test_capacity_drops_the_oldest_and_clamps_the_cursor(self):
        log = self.log_with([self.make(EventKind.LOW_POWER, frame=i) for i in range(3)],
                            capacity=2)
        events, cursor = log.new_since(0)
        self.assertEqual(len(events), 2, "最早的被挤掉了")
        self.assertEqual(cursor, 3, "游标仍按累计数走，不错位")

    def test_total_survives_the_capacity(self):
        log = self.log_with([self.make(EventKind.LOW_POWER) for _ in range(10)], capacity=3)
        self.assertEqual(len(log), 10)


class TestSummarize(unittest.TestCase):
    def make(self, kind, name="me", **data):
        return Event(kind=kind, frame=1, subject=Subject("house", 0, name), data=data)

    def test_empty_gives_empty_text(self):
        self.assertEqual(summarize(()), "")

    def test_same_kind_is_grouped_with_a_count(self):
        events = [self.make(EventKind.PLAYER_DEFEATED, name="A"),
                  self.make(EventKind.PLAYER_DEFEATED, name="B")]
        text = summarize(events)
        self.assertIn("玩家出局 ×2", text)
        self.assertIn("A", text)
        self.assertIn("B", text)

    def test_identical_details_are_listed_once(self):
        # 三个玩家同名时不该列三遍
        text = summarize([self.make(EventKind.PLAYER_DEFEATED, name="A")] * 3)
        self.assertEqual(text.count("A（电脑）"), 1)
        self.assertIn("×3", text)

    def test_long_groups_are_capped(self):
        events = [self.make(EventKind.PLAYER_DEFEATED, name=f"P{i}") for i in range(9)]
        text = summarize(events)
        self.assertIn("另有", text)
        self.assertEqual(text.count("被击败"), MAX_LISTED_PER_KIND)

    def test_permanent_kinds_keep_their_subject(self):
        text = summarize([self.make(EventKind.PLAYER_DEFEATED, name="Russia")])
        self.assertIn("Russia", text)
