"""常驻监听的测试。

它的存在理由本身就是一条实测结论：跑自动层、能发 `Wake` 的进程是**玩家自己的
MCP 服务进程**，agent 一空闲就没了——所以「出事了叫模型」必须由一个活得更久的
进程来做。
"""
import unittest

from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.engine.events import Event, EventKind, Subject
from ra2agent.engine.observation import Observation
from ra2agent.engine.state import GameState, MapData
from ra2agent.watch import wake_text, watch
from tests.fixtures import (PLAYER_HOUSE, build_game_state, build_house,
                            build_map_soa, build_object)


def make_map(side=9):
    cells = side * side
    return MapData.parse(build_map_soa(width=side, height=side,
                                       shrouded=[0] * cells,
                                       land=[LandType.CLEAR] * cells))


def event(kind, frame=100):
    return Event(kind=kind, frame=frame, subject=Subject("house", 0, "me"))


class TestWakeText(unittest.TestCase):
    """判据只有一份：技法层与监听进程共用 `watched_only`。"""

    def test_a_loss_is_worth_waking_for(self):
        self.assertIn("损失", wake_text((event(EventKind.OBJECT_LOST),)))

    def test_quiet_events_are_not(self):
        self.assertEqual(wake_text((event(EventKind.INSUFFICIENT_FUNDS),)), "")
        self.assertEqual(wake_text(()), "")


class StubClient:
    """按顺序吐出几帧的假客户端。"""

    def __init__(self, states):
        self._states = list(states)

    def read_map(self):
        return make_map()

    def read_object_types(self):
        return None

    def get_state(self):
        return self._states.pop(0)


def state_with(objects, number=100):
    return GameState.parse(build_game_state(
        houses=[build_house(PLAYER_HOUSE, current_player=True)],
        objects=list(objects), frame=number))


def tank(pointer=0xB1):
    return build_object(pointer, house=PLAYER_HOUSE,
                        object_type=AbstractType.UNIT, mission=Mission.GUARD,
                        x=300, y=300)


class TestWatchLoop(unittest.TestCase):
    def test_a_lost_unit_sends_one_wake_to_the_named_session(self):
        posted = []
        client = StubClient([state_with([tank()]), state_with([], number=110)])
        records = watch(0, "sess-alpha", interval=0, client=client,
                        poster=lambda endpoint, payload, timeout: (
                            posted.append(payload), (True, "ok"))[1],
                        stop_after=2)
        self.assertEqual(len(posted), 1)
        self.assertIn("损失", posted[0]["text"])
        self.assertEqual(posted[0]["session"], "sess-alpha")
        self.assertTrue(records[0]["sent"])

    def test_nothing_happening_sends_nothing(self):
        posted = []
        client = StubClient([state_with([tank()]), state_with([tank()], number=110)])
        watch(0, "sess", interval=0, client=client,
              poster=lambda e, p, t: (posted.append(p), (True, "ok"))[1],
              stop_after=2)
        self.assertEqual(posted, [])

    def test_the_session_is_carried_even_when_the_policy_is_default(self):
        """同机两个玩家：会话必须点名，否则插件会叫错人。"""
        from ra2agent.wake import WakePolicy
        posted = []
        client = StubClient([state_with([tank()]), state_with([], number=120)])
        watch(0, "sess-beta", interval=0, client=client,
              policy=WakePolicy(endpoint="http://127.0.0.1:1/x"),
              poster=lambda e, p, t: (posted.append(p), (True, "ok"))[1],
              stop_after=2)
        self.assertEqual(posted[0]["session"], "sess-beta")
        self.assertEqual(posted[0]["tactic"], "watch")


if __name__ == "__main__":
    unittest.main()
