"""`ra2agent.match` 的测试。

名册、整局起停与就绪判定全部离线：外部命令经 `runner`、探针经 `probe` 注入，
不碰 Windows、不碰网络。
"""
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace

from ra2agent.match import (STAGE_INGAME, MatchHost, MatchRoster, Participant,
                            ParticipantStatus, wsl_path)

ALPHA = {"name": "Alpha", "game_dir": "D:\\Games\\ra2probe",
         "probe_port": 14521, "side": 1, "color": 6}
BETA = {"name": "Beta", "game_dir": "D:\\Games\\ra2probe-b",
        "probe_port": 14522, "side": 0, "color": 1}


class Runner:
    """按调用顺序逐条回话的假执行器。"""

    def __init__(self, replies=()):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, argv, timeout=None):
        self.calls.append(argv)
        stdout = self.replies.pop(0) if self.replies else ""
        return SimpleNamespace(stdout=stdout, returncode=0)

    @property
    def argv(self):
        return self.calls


class Clock:
    """可拨的时钟，也当休眠函数用：睡过去就是把时间往前拨。"""

    def __init__(self, start=1000.0):
        self.now = start
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def make_roster(players=None, **overrides):
    """一份最小的名册。

    @param players: 参与者字典列表，默认 Alpha 与 Beta。
    @param overrides: 覆盖名册级字段。
    @returns: 名册。
    """
    data = {"map": "spawnmap.ini", "ready_timeout": 30.0, "launch_gap": 12.0,
            "players": players if players is not None else [ALPHA, BETA]}
    data.update(overrides)
    return MatchRoster(**{**data, "players": tuple(Participant(**p) for p in data["players"])})


class WslPathTest(unittest.TestCase):
    """Windows 路径到 WSL 挂载路径的映射。"""

    def test_maps_drive_letter(self):
        """盘符映射成 /mnt 下的同名小写目录。"""
        self.assertEqual(wsl_path("D:\\Games\\ra2probe"), "/mnt/d/Games/ra2probe")
        self.assertEqual(wsl_path("C:\\x"), "/mnt/c/x")

    def test_rejects_non_windows_path(self):
        """不是盘符开头的绝对路径应报错，而不是拼出一个坏路径。"""
        for bad in ("/mnt/d/x", "Games\\x", "\\\\server\\share"):
            with self.assertRaises(ValueError):
                wsl_path(bad)

    def test_participant_derives_wsl_dir(self):
        """参与者自己就能给出 WSL 侧目录。"""
        self.assertEqual(Participant(**ALPHA).wsl_dir, "/mnt/d/Games/ra2probe")


class RosterTest(unittest.TestCase):
    """名册的读取与校验。"""

    def setUp(self):
        """建一个临时目录。"""
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = pathlib.Path(self._dir.name) / "match.json"

    def write(self, data):
        """写入名册。

        @param data: 待写入的对象。
        """
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_loads_two_players(self):
        """正常名册读得出来。"""
        self.write({"map": "spawnmap.ini", "ready_timeout": 99.0, "launch_gap": 3.0,
                    "players": [ALPHA, BETA]})
        roster = MatchRoster.load(self.path)
        self.assertEqual([p.name for p in roster.players], ["Alpha", "Beta"])
        self.assertEqual(roster.ready_timeout, 99.0)
        self.assertEqual(roster.get("Beta").probe_port, 14522)

    def test_rejects_unknown_top_level_key(self):
        """认不出的顶层键报错，不静默忽略。"""
        self.write({"players": [ALPHA, BETA], "typo": 1})
        with self.assertRaises(ValueError) as ctx:
            MatchRoster.load(self.path)
        self.assertIn("typo", str(ctx.exception))

    def test_rejects_unknown_player_key(self):
        """参与者里认不出的键同样报错。"""
        self.write({"players": [ALPHA, {**BETA, "colour": 1}]})
        with self.assertRaises(ValueError) as ctx:
            MatchRoster.load(self.path)
        self.assertIn("colour", str(ctx.exception))

    def test_rejects_single_player(self):
        """一个参与者凑不成一局。"""
        self.write({"players": [ALPHA]})
        with self.assertRaises(ValueError):
            MatchRoster.load(self.path)

    def test_rejects_duplicate_names_and_ports(self):
        """名字与探针端口都必须各不相同。"""
        with self.assertRaises(ValueError):
            make_roster([ALPHA, {**BETA, "name": "Alpha"}]).validate()
        with self.assertRaises(ValueError):
            make_roster([ALPHA, {**BETA, "probe_port": 14521}]).validate()
        with self.assertRaises(ValueError):
            make_roster([ALPHA, {**BETA, "game_dir": ALPHA["game_dir"]}]).validate()

    def test_missing_file(self):
        """名册不存在时报错，而不是拿一份空名册去起局。"""
        with self.assertRaises(FileNotFoundError):
            MatchRoster.load(pathlib.Path(self._dir.name) / "nope.json")

    def test_get_unknown_name(self):
        """按名字取不到时报错，且列出有的名字。"""
        with self.assertRaises(KeyError) as ctx:
            make_roster().get("Gamma")
        self.assertIn("Alpha", str(ctx.exception))


class LaunchTest(unittest.TestCase):
    """整局启动。"""

    def make_host(self, replies=(), probe=None, clock=None):
        """一个外部调用全换掉的宿主。

        @param replies: 假执行器逐条回话的内容。
        @param probe: 假的探针读取函数。
        @param clock: 假时钟。
        @returns: (宿主, 假执行器, 假时钟)。
        """
        runner = Runner(replies)
        clock = clock or Clock()
        host = MatchHost(make_roster(), runner=runner, probe=probe or (lambda p: None),
                         sleep=clock.sleep, now=clock)
        return host, runner, clock

    def test_launches_every_participant_in_its_own_directory(self):
        """每个参与者都用自己那份目录与可执行文件启动。"""
        host, runner, _ = self.make_host(["111", "222"])
        pids = host.launch()
        self.assertEqual(pids, {"Alpha": 111, "Beta": 222})
        first, second = (" ".join(argv) for argv in runner.argv)
        self.assertIn("D:\\Games\\ra2probe", first)
        self.assertIn("D:\\Games\\ra2probe-b", second)
        self.assertNotIn("ra2probe-b", first)

    def test_waits_between_launches(self):
        """两次启动之间要隔 launch_gap，最后一个起完不再等。"""
        host, _, clock = self.make_host(["111", "222"])
        host.launch()
        self.assertEqual(clock.slept, [12.0])

    def test_pid_is_optional(self):
        """拿不到 PID 时如实记 None，不编一个数。"""
        host, _, _ = self.make_host(["", ""])
        self.assertEqual(host.launch(), {"Alpha": None, "Beta": None})


class StatusTest(unittest.TestCase):
    """逐参与者观测。"""

    def test_reports_stage_and_frame_per_participant(self):
        """每个参与者各报自己的阶段与帧。"""
        readings = {"Alpha": (STAGE_INGAME, 100), "Beta": (1, 0)}
        host, _, _ = self.make_host_and_probe(readings)
        statuses = host.status()
        self.assertEqual([(s.participant.name, s.stage, s.frame) for s in statuses],
                         [("Alpha", STAGE_INGAME, 100), ("Beta", 1, 0)])
        self.assertTrue(statuses[0].ready)
        self.assertFalse(statuses[1].ready)

    def make_host_and_probe(self, readings):
        """宿主 + 按参与者名字回话的假探针。

        @param readings: 名字到 (stage, frame) 的映射；缺的名字当读不到。
        @returns: (宿主, 假执行器, 假时钟)。
        """
        runner = Runner(["", ""])
        clock = Clock()
        host = MatchHost(make_roster(), runner=runner,
                         probe=lambda p: readings.get(p.name),
                         sleep=clock.sleep, now=clock)
        return host, runner, clock

    def test_attributes_pids_by_executable_path(self):
        """PID 丢了就按可执行文件路径找回，且只认自己的目录。"""
        scoped = ["100|D:\\Games\\ra2probe\\gamemd-spawn-ra2yrcpp.exe\r\n"
                  "200|D:\\Games\\ra2probe-b\\gamemd-spawn-ra2yrcpp.exe\r\n"]
        runner = Runner(scoped)
        host = MatchHost(make_roster(), runner=runner, probe=lambda p: None,
                         sleep=Clock().sleep, now=Clock())
        statuses = host.status()
        self.assertEqual([(s.participant.name, s.pid) for s in statuses],
                         [("Alpha", 100), ("Beta", 200)])
        self.assertEqual(len(runner.argv), 1, "每次 status 只该查一次进程归属")

    def test_ignores_paths_that_are_not_a_participant(self):
        """别人的同映像名进程不该被算进来。"""
        scoped = ["999|D:\\Elsewhere\\gamemd-spawn-ra2yrcpp.exe\r\n"]
        host = MatchHost(make_roster(), runner=Runner(scoped), probe=lambda p: None,
                         sleep=Clock().sleep, now=Clock())
        self.assertEqual([s.pid for s in host.status()], [None, None])

    def test_unreadable_probe_is_none(self):
        """探针读不到时阶段与帧都是 None，而不是 0。"""
        host, _, _ = self.make_host_and_probe({})
        status = host.status()[0]
        self.assertIsNone(status.stage)
        self.assertIsNone(status.frame)
        self.assertFalse(status.ready)


class WaitReadyTest(unittest.TestCase):
    """就绪判定。"""

    def make_host(self, rounds, ready_timeout=10.0):
        """造一个探针按轮回话的宿主。

        一轮 = 每个参与者各被读一次；轮数超出给的读数就重复最后一轮。

        @param rounds: 每轮返回的 {名字: (stage, frame)}。
        @param ready_timeout: 就绪等待上限（秒）。
        @returns: (宿主, 假时钟)。
        """
        roster = make_roster(ready_timeout=ready_timeout)
        clock = Clock()
        calls = {"n": 0}

        def probe(participant):
            index = min(calls["n"] // len(roster.players), len(rounds) - 1)
            calls["n"] += 1
            return rounds[index].get(participant.name)

        host = MatchHost(roster, runner=Runner([""] * 4), probe=probe,
                         sleep=clock.sleep, now=clock)
        return host, clock

    def test_returns_once_everyone_is_in_game(self):
        """两边都进对局即返回，且只在未就绪时等过一轮。"""
        host, clock = self.make_host([
            {"Alpha": (1, 0), "Beta": (1, 0)},
            {"Alpha": (STAGE_INGAME, 50), "Beta": (STAGE_INGAME, 49)},
        ])
        statuses = host.wait_ready()
        self.assertTrue(all(item.ready for item in statuses))
        self.assertEqual([item.frame for item in statuses], [50, 49])
        self.assertEqual(clock.slept, [2.0])

    def test_returns_immediately_when_already_ready(self):
        """已经就绪时一次也不等。"""
        host, clock = self.make_host([{"Alpha": (STAGE_INGAME, 1),
                                       "Beta": (STAGE_INGAME, 1)}])
        host.wait_ready()
        self.assertEqual(clock.slept, [])

    def test_times_out_and_names_the_pending(self):
        """超时报错要点出谁还没进对局，而不是只说超时。"""
        host, _ = self.make_host([{"Alpha": (STAGE_INGAME, 9), "Beta": (1, 0)}],
                                 ready_timeout=5.0)
        with self.assertRaises(TimeoutError) as ctx:
            host.wait_ready()
        message = str(ctx.exception)
        self.assertIn("['Beta']", message, "待就绪名单里只该有 Beta")


class StopTest(unittest.TestCase):
    """整局停止。"""

    def test_kills_only_the_recorded_pids(self):
        """按 PID 停，绝不按映像名——两个参与者的可执行文件同名。"""
        runner = Runner(["111", "222", "", ""])
        clock = Clock()
        host = MatchHost(make_roster(), runner=runner, probe=lambda p: None,
                         sleep=clock.sleep, now=clock)
        host.launch()
        killed = host.stop()
        self.assertEqual(sorted(killed), [111, 222])
        kills = [argv for argv in runner.argv if "taskkill" in argv[0].lower()]
        self.assertEqual(len(kills), 2)
        for argv in kills:
            self.assertIn("/PID", argv)
            self.assertNotIn("/IM", argv)

    def test_stop_without_processes_is_empty(self):
        """没有在跑的参与者时停是个空操作。"""
        runner = Runner([""])
        host = MatchHost(make_roster(), runner=runner, probe=lambda p: None,
                         sleep=Clock().sleep, now=Clock())
        self.assertEqual(host.stop(), ())
        self.assertFalse([a for a in runner.argv if "taskkill" in a[0].lower()])


class StatusShapeTest(unittest.TestCase):
    """`ParticipantStatus.ready` 的边界。"""

    def test_only_ingame_counts_as_ready(self):
        """加载中不算就绪。"""
        player = Participant(**ALPHA)
        self.assertTrue(ParticipantStatus(player, 1, True, STAGE_INGAME, 5).ready)
        self.assertFalse(ParticipantStatus(player, 1, True, 1, 0).ready)
        self.assertFalse(ParticipantStatus(player, 1, True, None, None).ready)


if __name__ == "__main__":
    unittest.main()
