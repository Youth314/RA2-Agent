"""`ra2agent.game` 的测试。

宿主侧的外部调用全部经 `runner` 注入，故不碰 Windows、不碰网络（只有端口探测
那两条用本地回环）。
"""
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from ra2agent.errors import Ra2Error
from ra2agent.game import (GAME_ARG, GAME_DIR, GAME_EXE, POWERSHELL, TASKKILL,
                           TASKLIST, GameHost, HostState, ProcessInfo,
                           describe_age, parse_processes)

CSV_ROW = '"gamemd-spawn-ra2yrcpp.exe","1234","Console","1","1,234 K"\r\n'
#: 没匹配时 tasklist 打一行本地化提示；它是 GBK，按 UTF-8 解出来是乱码。
NO_MATCH = "\ufffd\ufffd\ufffd: \ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\r\n"


class Runner:
    """记录 argv 的假执行器。"""

    def __init__(self, stdout="", error=None):
        self.stdout = stdout
        self.error = error
        self.calls = []

    def __call__(self, argv, timeout=None):
        self.calls.append((argv, timeout))
        if self.error is not None:
            raise self.error
        return SimpleNamespace(stdout=self.stdout, returncode=0)

    @property
    def argv(self):
        return [call[0] for call in self.calls]


class Clock:
    """可拨的时钟，用来摆布「本次启动」与「崩溃报告」的先后。"""

    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds
        return self.now


def make_host(stdout="", error=None, **kwargs):
    """一个外部调用全部换掉的宿主。

    端口探针默认返回「没在听」：下面几条断言的是「进程在、端口还没通」，而真去连
    会连到本机正在跑的那一局（14521），结论随游戏开关而变。
    """
    runner = Runner(stdout, error)
    kwargs.setdefault("focus_probe", lambda: True)
    kwargs.setdefault("focus_reset", lambda: True)
    kwargs.setdefault("crash_report", "/nonexistent")
    kwargs.setdefault("port_probe", lambda: False)
    return GameHost(runner=runner, **kwargs), runner


# ---------------------------------------------------------------- 解析
class TestParseProcesses(unittest.TestCase):
    def test_reads_pid(self):
        self.assertEqual(parse_processes(CSV_ROW),
                         (ProcessInfo(image=GAME_EXE, pid=1234),))

    def test_ignores_the_no_match_notice(self):
        # 提示行是 GBK 的，按 UTF-8 解出来是乱码；只认引号开头的 CSV 行
        self.assertEqual(parse_processes(NO_MATCH), ())

    def test_ignores_empty_and_junk(self):
        for text in ("", None, "not a csv line", '"name","not-a-pid"'):
            with self.subTest(text=text):
                self.assertEqual(parse_processes(text), ())

    def test_reads_several_rows(self):
        rows = parse_processes(CSV_ROW + '"gamemd-spawn-ra2yrcpp.exe","99","Console","1","1 K"\r\n')
        self.assertEqual([row.pid for row in rows], [1234, 99])


class TestDescribeAge(unittest.TestCase):
    def test_buckets(self):
        self.assertEqual(describe_age(5), "5 秒前")
        self.assertEqual(describe_age(90), "1 分钟前")
        self.assertEqual(describe_age(7200), "2 小时前")
        self.assertEqual(describe_age(200000), "2 天前")


# ---------------------------------------------------------------- 命令
class TestCommands(unittest.TestCase):
    def test_processes_filters_by_image_and_asks_for_csv(self):
        host, runner = make_host()
        host.processes()
        (argv, _), = runner.calls
        self.assertEqual(argv[0], TASKLIST)
        self.assertIn(f"IMAGENAME eq {GAME_EXE}", argv)
        self.assertIn("CSV", argv)

    def test_launch_uses_powershell_with_absolute_paths(self):
        # `cmd /c start` 从 WSL 启动会静默失败，故只能是这条
        host, runner = make_host()
        host.launch()
        (argv, _), = runner.calls
        self.assertEqual(argv[0], POWERSHELL)
        self.assertIn(f"{GAME_DIR}\\{GAME_EXE}", " ".join(argv))
        self.assertIn(GAME_ARG, " ".join(argv))

    def test_terminate_kills_by_image_and_reports_pids(self):
        host, runner = make_host(CSV_ROW)
        self.assertEqual(host.terminate(), (1234,))
        self.assertEqual(runner.argv[1][0], TASKKILL)
        self.assertIn("/F", runner.argv[1])

    def test_terminate_is_a_no_op_without_processes(self):
        host, runner = make_host(NO_MATCH)
        self.assertEqual(host.terminate(), ())
        self.assertEqual(len(runner.argv), 1)          # 只查了进程，没有 taskkill

    def test_missing_windows_interop_becomes_readable(self):
        host, _ = make_host(error=FileNotFoundError("tasklist.exe"))
        with self.assertRaises(Ra2Error) as ctx:
            host.processes()
        self.assertIn("Windows 互操作", str(ctx.exception))

    def test_command_timeout_becomes_readable(self):
        host, _ = make_host(error=subprocess.TimeoutExpired("tasklist.exe", 30))
        with self.assertRaises(Ra2Error) as ctx:
            host.processes()
        self.assertIn("超时", str(ctx.exception))


# ---------------------------------------------------------------- 端口与留证
class TestProbes(unittest.TestCase):
    def test_port_open_against_a_real_listener(self):
        # 唯一一处要真连的：探针传 None，回到 socket 实现（`make_host` 默认给它假的）
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]
            host, _ = make_host(port=port, port_probe=None)
            self.assertTrue(host.port_open())
        # 端口 1 上不会有服务在听
        closed, _ = make_host(port=1, port_probe=None)
        self.assertFalse(closed.port_open())

    def test_crash_report_age_reads_mtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "EXCEPT_CNCNET.TXT"
            report.write_text("boom", encoding="utf-8")
            host, _ = make_host(crash_report=str(report), now=lambda: report.stat().st_mtime + 2820)
            self.assertAlmostEqual(host.crash_report_age(), 2820, delta=1)

    def test_missing_crash_report_is_none(self):
        host, _ = make_host()
        self.assertIsNone(host.crash_report_age())


# ---------------------------------------------------------------- 巡检
class TestInspect(unittest.TestCase):
    def test_no_process_skips_the_focus_probe(self):
        calls = []
        host, _ = make_host(focus_probe=lambda: calls.append(1) or True)
        state = host.inspect()
        self.assertFalse(state.running)
        self.assertIsNone(state.focused)
        self.assertEqual(calls, [])

    def test_no_process_says_how_to_start(self):
        host, _ = make_host()
        lines = host.describe(host.inspect())
        self.assertIn("未运行", lines[0])
        self.assertIn("game start", " ".join(lines))

    def test_process_without_the_port_is_still_loading(self):
        host, _ = make_host(CSV_ROW)
        text = "\n".join(host.describe(host.inspect()))
        self.assertIn("1234", text)
        self.assertIn("正在启动", text)
        self.assertIn("还没通", text)

    def test_the_startup_line_says_how_long_it_has_waited(self):
        # 模型刚 start 完就查，看到「已等 N 秒」才知道该等而不是判崩
        clock = Clock(1000.0)
        host, _ = make_host(CSV_ROW, now=clock)
        host.launched_at = clock.now
        clock.advance(4)
        text = "\n".join(host.describe(host.inspect()))
        self.assertIn("已等 4 秒", text)

    def test_startup_grace_note_only_after_a_minute(self):
        clock = Clock(1000.0)
        host, _ = make_host(CSV_ROW, now=clock)
        host.launched_at = clock.now
        clock.advance(30)
        self.assertNotIn("可能卡住", "\n".join(host.describe(host.inspect())))
        clock.advance(60)
        self.assertIn("可能卡住", "\n".join(host.describe(host.inspect())))

    def test_port_probe_is_injectable(self):
        # 真去连会连到本机正在跑的那一局，结论随游戏开关而变；故探针必须能换掉
        host, _ = make_host(CSV_ROW, port_probe=lambda: True)
        self.assertIn("服务在听", "\n".join(host.describe(host.inspect())))

    def test_crash_report_from_before_this_launch_is_hidden(self):
        # 刚起游戏那几秒提一份旧报告，模型会把「正在启动」读成「崩过」
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "EXCEPT_CNCNET.TXT"
            report.write_text("boom", encoding="utf-8")
            clock = Clock(report.stat().st_mtime)
            host, _ = make_host(crash_report=str(report), now=clock)
            host.launched_at = clock.advance(3600)          # 一小时之后才启动
            clock.advance(5)
            self.assertIsNone(host.inspect().crash_age)

    def test_crash_report_after_this_launch_is_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "EXCEPT_CNCNET.TXT"
            report.write_text("boom", encoding="utf-8")
            clock = Clock(report.stat().st_mtime)
            host, _ = make_host(crash_report=str(report), now=clock)
            host.launched_at = clock.now
            report.touch()                                  # 启动之后才崩
            clock.advance(5)
            self.assertAlmostEqual(host.inspect().crash_age, 5, delta=1)

    def test_crash_report_alone_still_reported_when_we_never_launched(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "EXCEPT_CNCNET.TXT"
            report.write_text("boom", encoding="utf-8")
            clock = Clock(report.stat().st_mtime + 600)
            host, _ = make_host(crash_report=str(report), now=clock)
            self.assertAlmostEqual(host.inspect().crash_age, 600, delta=1)

    def test_running_and_focused(self):
        host, _ = make_host(CSV_ROW)
        state = HostState(processes=(ProcessInfo(GAME_EXE, 1),), listening=True,
                          crash_age=None, focused=True)
        self.assertIn("窗口在前台", host.describe(state)[0])

    def test_running_and_blurred_points_at_focus(self):
        host, _ = make_host(CSV_ROW)
        state = HostState(processes=(ProcessInfo(GAME_EXE, 1),), listening=True,
                          crash_age=None, focused=False)
        self.assertIn("game focus", host.describe(state)[0])

    def test_crash_evidence_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "EXCEPT_CNCNET.TXT"
            report.write_text("boom", encoding="utf-8")
            host, _ = make_host(crash_report=str(report),
                                now=lambda: report.stat().st_mtime + 2820)
            evidence = host.describe(host.inspect())[-1]
        self.assertIn("崩溃报告 47 分钟前", evidence)
        self.assertIn(str(report), evidence)


if __name__ == "__main__":
    unittest.main()
