"""MCP 服务的测试。

协议层完全离线：喂 JSON-RPC 行进去，看吐出来什么。游戏的连接是假的，故启动
路径也不碰网络——这正是要保证的性质（DSH 会先用探针进程列工具，那时游戏可能没开）。
"""
import io
import json
import unittest

from ra2agent.errors import Ra2Error
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
    def test_lists_four_tools(self):
        [response] = serve([request(1, "tools/list")])
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["status", "tactics", "call", "cancel"])

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
                         ("status", "tactics", "call", "cancel"))

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


if __name__ == "__main__":
    unittest.main()
