"""事件合成的测试。

关键是**纯函数**：同样的前后两帧必须给出同样的事件。回放场景存的是原始帧，
离线闭环要靠它重新合成事件来验证「事件触发的技法」。
"""
import unittest

from ra2agent.events import EventKind, Policy, detect
from ra2agent.observation import Observation
from ra2agent.state import GameState
from tests.fixtures import (ENEMY_HOUSE, NEUTRAL_HOUSE, PLAYER_HOUSE,
                            build_game_state, build_house)


def frame(houses, frame_number=100):
    """一帧观测。第一个阵营当己方。"""
    state = GameState.parse(build_game_state(houses=list(houses), frame=frame_number))
    return Observation(frame=state.frame, house=state.player_house(), state=state)


def me(**kwargs):
    """己方阵营，默认一个玩家。"""
    return build_house(PLAYER_HOUSE, current_player=True, **kwargs)


def other(**kwargs):
    return build_house(ENEMY_HOUSE, **kwargs)


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
