"""MCP 服务的测试。

协议层完全离线：喂 JSON-RPC 行进去，看吐出来什么。游戏的连接是假的，故启动
路径也不碰网络——这正是要保证的性质（DSH 会先用探针进程列工具，那时游戏可能没开）。
"""
import io
import json
import time
import unittest
from types import SimpleNamespace

from ra2agent.constants import LoadStage
from ra2agent.errors import Ra2Error
from ra2agent.game import GameHost, ProcessInfo
from ra2agent.mcp import (FALLBACK_PROTOCOL, INSTRUCTIONS, LATEST_PROTOCOL,
                          PROTOCOL_VERSIONS, TOOLS, GameSession, McpServer)


class FakeSession:
    """假会话：不连游戏，记录调用。"""

    def __init__(self, error=None):
        self.calls = []
        self.error = error

    def tool_names(self):
        return tuple(tool["name"] for tool in TOOLS)

    def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error is not None:
            raise self.error
        return f"{name} 的结果"


def serve(lines, session=None):
    """把若干行喂给服务器，返回它写出的响应列表。"""
    out = io.StringIO()
    server = McpServer(session or FakeSession(), stdin=io.StringIO("\n".join(lines) + "\n"),
                       stdout=out)
    server.serve_forever()
    return [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]


def request(identifier, method, params=None):
    message = {"jsonrpc": "2.0", "id": identifier, "method": method}
    if params is not None:
        message["params"] = params
    return json.dumps(message)


# ---------------------------------------------------------------- 握手
class TestInitialize(unittest.TestCase):
    def test_handshake_shape(self):
        [response] = serve([request(1, "initialize",
                                    {"protocolVersion": LATEST_PROTOCOL,
                                     "capabilities": {}})])
        result = response["result"]
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(result["protocolVersion"], LATEST_PROTOCOL)
        self.assertEqual(result["serverInfo"]["name"], "ra2agent")
        self.assertIn("tools", result["capabilities"])
        self.assertIn("status", result["instructions"])

    def test_echoes_known_version(self):
        old = PROTOCOL_VERSIONS[-1]
        [response] = serve([request(1, "initialize", {"protocolVersion": old})])
        self.assertEqual(response["result"]["protocolVersion"], old)

    def test_unknown_version_falls_back_to_a_legacy_one(self):
        # 回 LATEST 会让 legacy 握手拒连（SDK 只接受 pre-2026 的版本）
        [response] = serve([request(1, "initialize",
                                    {"protocolVersion": "1999-01-01"})])
        self.assertEqual(response["result"]["protocolVersion"], FALLBACK_PROTOCOL)
        self.assertLess(FALLBACK_PROTOCOL, LATEST_PROTOCOL)

    def test_answers_the_version_dsh_offers(self):
        for version in ("2026-07-28", "2025-11-25"):
            with self.subTest(version=version):
                [response] = serve([request(1, "initialize",
                                            {"protocolVersion": version})])
                self.assertEqual(response["result"]["protocolVersion"], version)

    def test_ping(self):
        [response] = serve([request(2, "ping")])
        self.assertEqual(response["result"], {})


# ---------------------------------------------------------------- 工具表
class TestToolList(unittest.TestCase):
    def test_lists_tools(self):
        [response] = serve([request(1, "tools/list")])
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["status", "tactics", "call", "cancel", "game"])

    def test_every_tool_has_schema(self):
        [response] = serve([request(1, "tools/list")])
        for tool in response["result"]["tools"]:
            with self.subTest(tool=tool["name"]):
                self.assertTrue(tool["description"])
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertFalse(tool["inputSchema"]["additionalProperties"])

    def test_startup_does_not_touch_the_session(self):
        # 列工具不能连游戏：DSH 会先起一个探针进程
        session = FakeSession()
        serve([request(1, "initialize", {}), request(2, "tools/list")], session)
        self.assertEqual(session.calls, [])

    def test_instructions_are_short(self):
        self.assertLess(len(INSTRUCTIONS.encode()), 1024)


# ---------------------------------------------------------------- 调用
class TestToolCall(unittest.TestCase):
    def test_status_passes_through(self):
        session = FakeSession()
        [response] = serve([request(1, "tools/call",
                                    {"name": "status", "arguments": {}})], session)
        self.assertEqual(session.calls, [("status", {})])
        self.assertEqual(response["result"]["content"][0]["text"], "status 的结果")
        self.assertNotIn("isError", response["result"])

    def test_tactics_passes_query(self):
        session = FakeSession()
        serve([request(1, "tools/call",
                       {"name": "tactics", "arguments": {"query": "推进"}})], session)
        self.assertEqual(session.calls, [("tactics", {"query": "推进"})])

    def test_runtime_error_becomes_iserror_text(self):
        session = FakeSession(error=Ra2Error("游戏没开"))
        [response] = serve([request(1, "tools/call",
                                    {"name": "status", "arguments": {}})], session)
        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("游戏没开", result["content"][0]["text"])

    def test_unknown_tool_is_a_protocol_error(self):
        [response] = serve([request(1, "tools/call",
                                    {"name": "nope", "arguments": {}})])
        self.assertEqual(response["error"]["code"], -32602)

    def test_missing_arguments_default_to_empty(self):
        session = FakeSession()
        serve([request(1, "tools/call", {"name": "status"})], session)
        self.assertEqual(session.calls, [("status", {})])


# ---------------------------------------------------------------- 协议杂项
class TestProtocol(unittest.TestCase):
    def test_notification_gets_no_response(self):
        out = serve(['{"jsonrpc":"2.0","method":"notifications/initialized"}'])
        self.assertEqual(out, [])

    def test_malformed_json(self):
        [response] = serve(["{ 不是 json"])
        self.assertEqual(response["error"]["code"], -32700)
        self.assertIsNone(response["id"])

    def test_unknown_method(self):
        [response] = serve([request(9, "resources/list")])
        self.assertEqual(response["error"]["code"], -32601)

    def test_tool_exception_becomes_text_and_loop_survives(self):
        class Exploding(FakeSession):
            def call_tool(self, name, arguments):
                raise RuntimeError("炸了")

        responses = serve([request(1, "tools/call", {"name": "status"}),
                           request(2, "ping")], Exploding())
        self.assertTrue(responses[0]["result"]["isError"])
        self.assertIn("RuntimeError", responses[0]["result"]["content"][0]["text"])
        self.assertEqual(responses[1]["result"], {})       # 循环没有倒

    def test_connection_failure_is_a_tool_error(self):
        # 游戏没开时最常见的失败：要回文本说明，不能让模型看到协议错误
        session = FakeSession(error=ConnectionRefusedError("连不上 14521"))
        [response] = serve([request(1, "tools/call",
                                    {"name": "status", "arguments": {}})], session)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("ConnectionRefusedError", response["result"]["content"][0]["text"])

    def test_several_messages_in_order(self):
        responses = serve([request(1, "ping"), request(2, "tools/list"),
                           request(3, "ping")])
        self.assertEqual([r["id"] for r in responses], [1, 2, 3])


# ---------------------------------------------------------------- 会话
class TestGameSession(unittest.TestCase):
    def test_tool_names_match_the_table(self):
        self.assertEqual(GameSession().tool_names(),
                         ("status", "tactics", "call", "cancel", "game"))

    def test_unknown_tool_raises(self):
        session = GameSession()
        session.ensure = lambda: session            # 跳过真连接
        with self.assertRaises(ValueError):
            session.call_tool("nope", {})

    def test_call_arguments_are_validated(self):
        session = GameSession()
        session.ensure = lambda: session
        session._commander = object()               # 不会走到它
        with self.assertRaises(ValueError) as ctx:
            session._call({"calls": [{"units": [1]}]})
        self.assertIn("缺少 tactic", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            session._call({"calls": [{"tactic": "a", "typo": 1}]})
        self.assertIn("不认识的字段", str(ctx.exception))


# ---------------------------------------------------------------- 门外
class FakeHost(GameHost):
    """离线替身：外部调用全换掉，只留 `inspect`/`describe` 的真实拼装。"""

    def __init__(self, processes=(), listening=False, focused=True, crash_age=None,
                 windows=(), focus_ok=True, focus_route="按进程 7 认准"):
        super().__init__(runner=lambda argv, timeout=None: None,
                         focus_probe=lambda: focused,
                         focus_reset=lambda: focus_ok,
                         window_probe=lambda: tuple(windows),
                         crash_report="/nonexistent")
        self._processes = processes
        self._listening = listening
        self._crash_age = crash_age
        self._focus_ok = focus_ok
        self.last_focus_route = focus_route
        self.launched = False
        self.terminated = False
        self.focus_calls = 0

    def processes(self):
        return self._processes

    def port_open(self):
        return self._listening

    def crash_report_age(self):
        return self._crash_age

    def launch(self):
        self.launched = True

    def terminate(self):
        self.terminated = True
        return tuple(process.pid for process in self._processes)

    def focus_game(self):
        self.focus_calls += 1
        return self._focus_ok


def game_session(**host_kwargs):
    """一个不连游戏的会话，宿主侧换成替身。"""
    host = FakeHost(**host_kwargs)
    return GameSession(game_host=host), host


def in_match(frame=812, stage=LoadStage.INGAME):
    """一个「已进对局」的假观测。"""
    state = SimpleNamespace(stage=stage, frame=frame, player_house=lambda: object())
    return SimpleNamespace(state=state, frame=frame,
                           house=SimpleNamespace(name="America"))


def refuse_connection():
    raise ConnectionRefusedError("拒绝连接")


class TestGameTool(unittest.TestCase):
    def test_status_reports_no_game_and_how_to_start(self):
        session, _ = game_session()
        text = session.call_tool("game", {"action": "status"})
        self.assertIn("未运行", text)
        self.assertIn("game start", text)

    def test_status_does_not_connect(self):
        # 门外动作必须在没有对局时也能用，故不能 ensure()
        session, _ = game_session()
        session.ensure = lambda: self.fail("game status 不该连游戏")
        session.call_tool("game", {"action": "status"})

    def test_status_lists_pids_and_focus_when_running(self):
        session, _ = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 1234),),
            listening=True, focused=False)
        text = session.call_tool("game", {"action": "status"})
        self.assertIn("1234", text)
        self.assertIn("窗口不在前台", text)
        self.assertNotIn("主循环暂停", text)      # 前台判据推不出暂停

    def test_loop_line_reports_advancing_frames(self):
        """主循环按**帧号推进**判，而不是按窗口在不在前台。"""
        session, _ = game_session()
        session._frame_sample = (100, time.monotonic())
        line = session._loop_line(150)
        self.assertIn("在跑", line)
        self.assertIn("100→150", line)

    def test_loop_line_reports_a_stall_only_after_the_threshold(self):
        session, _ = game_session()
        session._frame_sample = (100, time.monotonic())
        self.assertIn("没变", session._loop_line(100))       # 还没到阈值
        session._frame_sample = (100, time.monotonic() - 30.0)
        stalled = session._loop_line(100)
        self.assertIn("疑似暂停", stalled)
        self.assertIn("game focus", stalled)

    def test_status_appends_the_match_line_when_connected(self):
        session, _ = game_session(listening=True)
        session._observation = in_match()
        text = session.call_tool("game", {"action": "status"})
        self.assertIn("帧 812", text)
        self.assertIn("阵营 America", text)

    def test_status_hides_a_broken_connection(self):
        session, _ = game_session(listening=True)
        session._observation = in_match()
        session._broken = True
        self.assertNotIn("帧 812", session.call_tool("game", {"action": "status"}))

    def test_tactics_stamps_the_frame(self):
        """卡片是按**那一刻**的局面筛的，故输出带帧号。

        不带帧号，「上一拍还看不见、这一拍又出现了」这种争论就永远说不清
        （实测卡过一次：一方说没建造厂时卡片就在，另一方怎么都复现不出来）。
        """
        session, _ = game_session()
        session.ensure = lambda: session
        session._observation = in_match(frame=333)
        session._commander = SimpleNamespace(
            tactics=lambda query, observation: (
                SimpleNamespace(text=lambda: "推进卡片"),))
        text = session.call_tool("tactics", {})
        self.assertIn("帧 333", text)
        self.assertIn("推进卡片", text)
    def test_status_reports_crash_evidence(self):
        session, _ = game_session(crash_age=2820)
        self.assertIn("崩溃报告 47 分钟前",
                      session.call_tool("game", {"action": "status"}))

    def test_start_launches_and_drops_a_stale_session(self):
        session, host = game_session()
        session._broken = True
        text = session.call_tool("game", {"action": "start"})
        self.assertTrue(host.launched)
        self.assertIn("已发起启动", text)
        self.assertFalse(session._broken)

    def test_start_is_idempotent(self):
        session, host = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),))
        text = session.call_tool("game", {"action": "start"})
        self.assertFalse(host.launched)
        self.assertIn("已经在跑", text)

    def test_stop_refuses_during_a_match_without_force(self):
        session, host = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),))
        session._observation = in_match()
        text = session.call_tool("game", {"action": "stop"})
        self.assertFalse(host.terminated)
        self.assertIn("force=true", text)

    def test_stop_with_force_kills_and_resets(self):
        session, host = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),))
        session._observation = in_match()
        text = session.call_tool("game", {"action": "stop", "force": True})
        self.assertTrue(host.terminated)
        self.assertIn("已停止游戏", text)

    def test_stop_without_a_match_needs_no_force(self):
        session, host = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),))
        session._observation = in_match(stage=LoadStage.LOADING)
        self.assertIn("已停止游戏", session.call_tool("game", {"action": "stop"}))
        self.assertTrue(host.terminated)

    def test_stop_when_not_running_is_a_no_op(self):
        session, host = game_session()
        self.assertIn("无需停止", session.call_tool("game", {"action": "stop"}))
        self.assertFalse(host.terminated)

    def test_focus_requires_a_running_game(self):
        session, host = game_session()
        self.assertIn("没在跑", session.call_tool("game", {"action": "focus"}))
        self.assertEqual(host.focus_calls, 0)

    def test_focus_resets_when_running(self):
        session, host = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),))
        self.assertIn("已把游戏窗口置前",
                      session.call_tool("game", {"action": "focus"}))
        self.assertEqual(host.focus_calls, 1)

    def test_focus_reports_which_route_it_took(self):
        """同桌面两个同名实例时，说清是「按进程认准」还是「按标题取第一个」。"""
        session, _ = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),),
            windows=((11, "Yuri's Revenge"), (22, "Yuri's Revenge")),
            focus_route="按进程 7 认准")
        text = session.call_tool("game", {"action": "focus"})
        self.assertIn("已把游戏窗口置前", text)
        self.assertIn("按进程 7 认准", text)

    def test_focus_warns_when_it_could_only_guess_by_title(self):
        session, _ = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),),
            windows=((11, "Yuri's Revenge"), (22, "Yuri's Revenge")),
            focus_route="按标题取第一个（同名实例分辨不出是哪一份）")
        text = session.call_tool("game", {"action": "focus"})
        self.assertIn("分辨不出是哪一份", text)

    def test_focus_failure_says_what_it_found(self):
        """置前失败时别只说「没找到？」——找到几个、成没成要分开说。"""
        session, _ = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),),
            windows=((11, "Yuri's Revenge"),), focus_ok=False)
        text = session.call_tool("game", {"action": "focus"})
        self.assertIn("找到 1 个同名窗口", text)
        self.assertNotIn("没找到", text)

    def test_focus_failure_without_any_window_says_not_found(self):
        session, _ = game_session(
            processes=(ProcessInfo("gamemd-spawn-ra2yrcpp.exe", 7),),
            windows=(), focus_ok=False)
        self.assertIn("没找到", session.call_tool("game", {"action": "focus"}))

    def test_unknown_action_is_a_value_error(self):
        session, _ = game_session()
        with self.assertRaises(ValueError):
            session.call_tool("game", {"action": "restart"})

    def test_bad_action_reaches_the_model_as_plain_text(self):
        # 参数错误是模型自己造成的，报错不该以 ValueError 开头
        session, _ = game_session()
        [response] = serve([request(1, "tools/call",
                                    {"name": "game",
                                     "arguments": {"action": "restart"}})],
                           session)
        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertTrue(result["content"][0]["text"].startswith("没有这个 action"))

    def test_project_errors_are_not_prefixed_with_a_class_name(self):
        session = FakeSession(error=Ra2Error("游戏没在跑：端口不通"))
        [response] = serve([request(1, "tools/call",
                                    {"name": "status", "arguments": {}})], session)
        self.assertEqual(response["result"]["content"][0]["text"], "游戏没在跑：端口不通")

    def test_in_game_tools_point_at_game_when_disconnected(self):
        session, _ = game_session()
        session._connect = refuse_connection
        with self.assertRaises(Ra2Error) as ctx:
            session.call_tool("status", {})
        message = str(ctx.exception)
        self.assertIn("游戏没在跑", message)
        self.assertIn("game start", message)


if __name__ == "__main__":
    unittest.main()


class ResolvePlayerTest(unittest.TestCase):
    """`--player` 从名册取该玩家的目录与端口。"""

    def setUp(self):
        """写一份临时名册。"""
        import pathlib
        import tempfile
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.roster = pathlib.Path(self._dir.name) / "match.json"
        self.roster.write_text(json.dumps({"players": [
            {"name": "Alpha", "game_dir": "D:\\Games\\ra2probe",
             "probe_port": 14521, "match_port": 15000, "side": 1, "color": 6},
            {"name": "Beta", "game_dir": "D:\\Games\\ra2probe-b",
             "probe_port": 14522, "match_port": 15001, "side": 0, "color": 1},
        ]}), encoding="utf-8")

    def test_port_and_dir_come_from_the_roster(self):
        """两个玩家各自拿到自己那份端口与目录，而不是模块常量。"""
        from ra2agent.mcp import resolve_player

        alpha_port, alpha = resolve_player("Alpha", self.roster)
        beta_port, beta = resolve_player("Beta", self.roster)
        self.assertEqual((alpha_port, beta_port), (14521, 14522))
        self.assertEqual(alpha.game_dir, "D:\\Games\\ra2probe")
        self.assertEqual(beta.game_dir, "D:\\Games\\ra2probe-b")
        self.assertEqual(beta.game_dir_wsl, "/mnt/d/Games/ra2probe-b")
        self.assertIn("ra2probe-b", beta.crash_report)

    def test_explicit_port_wins(self):
        """命令行显式给的端口优先于名册。"""
        from ra2agent.mcp import resolve_player

        port, host = resolve_player("Beta", self.roster, port=19999)
        self.assertEqual(port, 19999)
        self.assertEqual(host.port, 19999)

    def test_unknown_player_is_an_error(self):
        """名册里没有的玩家要报错，而不是悄悄用默认值。"""
        from ra2agent.mcp import resolve_player

        with self.assertRaises(KeyError):
            resolve_player("Gamma", self.roster)

    def test_missing_roster_is_an_error(self):
        """名册不存在时报错，而不是退回单实例常量。"""
        import pathlib
        from ra2agent.mcp import resolve_player

        with self.assertRaises(FileNotFoundError):
            resolve_player("Alpha", pathlib.Path(self._dir.name) / "nope.json")


class WakeSessionTest(unittest.TestCase):
    """唤醒目标会话可以显式指定。"""

    def test_session_override_lands_in_the_bridge(self):
        """`wake_session` 覆盖 `config/wake.json` 里的值。"""
        session = GameSession(wake_session="sess-beta")
        bridge = session._build_wake(None)
        self.assertEqual(bridge.policy.session, "sess-beta")

    def test_no_override_keeps_the_file_value(self):
        """不给覆盖时保持文件里的值（此处是默认空串）。"""
        session = GameSession()
        bridge = session._build_wake(None)
        self.assertEqual(bridge.policy.session, "")
