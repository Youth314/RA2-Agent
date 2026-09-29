"""唤醒桥的测试。

一次唤醒就是一轮 LLM 调用，是稀缺资源，故测试盯三件事：别刷屏、别丢内容、
失败了别装成功。
"""
import json
import pathlib
import tempfile
import unittest

from ra2agent.wake import WakeBridge, WakePolicy


class FakePoster:
    """记账用的假投递。"""

    def __init__(self, ok=True, body='{"ok": true}'):
        self.calls = []
        self.ok = ok
        self.body = body

    def __call__(self, endpoint, payload, timeout):
        self.calls.append((endpoint, payload, timeout))
        return self.ok, self.body


class WakeCase(unittest.TestCase):
    def build(self, poster=None, **policy):
        self.poster = poster or FakePoster()
        self.bridge = WakeBridge(policy=WakePolicy(**policy), poster=self.poster)
        return self.bridge


class TestDelivery(WakeCase):
    def test_sends_the_text(self):
        self.build()
        record = self.bridge.request("基地被打", frame=100, tactic="watch")
        self.assertTrue(record["sent"])
        self.assertEqual(len(self.poster.calls), 1)
        payload = self.poster.calls[0][1]
        self.assertIn("基地被打", payload["text"])
        self.assertEqual(payload["frame"], 100)
        self.assertEqual(payload["tactic"], "watch")

    def test_empty_text_is_not_sent(self):
        self.build()
        record = self.bridge.request("   ", frame=100)
        self.assertEqual(self.poster.calls, [])
        self.assertEqual(record["skipped"], "空说明")

    def test_endpoint_comes_from_the_policy(self):
        self.build(endpoint="http://127.0.0.1:9999/x")
        self.bridge.request("hi", frame=1)
        self.assertEqual(self.poster.calls[0][0], "http://127.0.0.1:9999/x")


class TestThrottle(WakeCase):
    def test_second_wake_too_soon_is_deferred(self):
        self.build(min_frames=180)
        self.bridge.request("第一条", frame=100)
        record = self.bridge.request("第二条", frame=150)
        self.assertFalse(record.get("sent"))
        self.assertIn("deferred", record)
        self.assertEqual(len(self.poster.calls), 1, "只投了一次")

    def test_deferred_content_is_not_lost(self):
        self.build(min_frames=180)
        self.bridge.request("第一条", frame=100)
        self.bridge.request("第二条", frame=150)
        self.assertEqual(self.bridge.pending, ("第二条",))
        self.bridge.request("第三条", frame=400)
        self.assertEqual(len(self.poster.calls), 2)
        merged = self.poster.calls[1][1]["text"]
        self.assertIn("第二条", merged)
        self.assertIn("第三条", merged)
        self.assertEqual(self.bridge.pending, (), "送出去之后待发队列清空")

    def test_budget_limits_the_match(self):
        self.build(min_frames=1, max_per_match=2)
        self.assertTrue(self.bridge.request("a", frame=1)["sent"])
        self.assertTrue(self.bridge.request("b", frame=10)["sent"])
        record = self.bridge.request("c", frame=20)
        self.assertIn("额度用尽", record["skipped"])
        self.assertEqual(len(self.poster.calls), 2)

    def test_first_wake_is_never_throttled(self):
        self.build(min_frames=100000)
        self.assertTrue(self.bridge.request("a", frame=1)["sent"])

    def test_pending_queue_is_bounded(self):
        self.build(min_frames=100000, max_pending=2)
        self.bridge.request("第一条", frame=1)
        for index in range(5):
            self.bridge.request(f"后续{index}", frame=2)
        self.assertLessEqual(len(self.bridge.pending), 2)


class TestFailure(WakeCase):
    def test_delivery_failure_is_reported_not_hidden(self):
        self.build(poster=FakePoster(ok=False, body="连接被拒绝"))
        record = self.bridge.request("基地被打", frame=100)
        self.assertFalse(record["sent"])
        self.assertIn("连接被拒绝", record["error"])

    def test_failed_content_is_retried_later(self):
        # 静默丢事件比报错糟得多
        self.build(poster=FakePoster(ok=False), min_frames=10)
        self.bridge.request("要紧的事", frame=100)
        self.assertEqual(self.bridge.pending, ("要紧的事",))
        self.poster.ok = True
        self.bridge.request("又一件", frame=200)
        self.assertIn("要紧的事", self.poster.calls[-1][1]["text"])

    def test_sent_counter_only_counts_success(self):
        self.build(poster=FakePoster(ok=False), min_frames=1)
        self.bridge.request("a", frame=1)
        self.assertEqual(self.bridge.sent, 0)

    def test_records_are_bounded(self):
        self.build(min_frames=1)
        self.bridge.max_records = 3
        for index in range(10):
            self.bridge.request(f"第{index}条", frame=index * 10)
        self.assertLessEqual(len(self.bridge.records), 3)


class TestPolicyConfig(unittest.TestCase):
    def load(self, payload):
        directory = tempfile.mkdtemp()
        path = pathlib.Path(directory) / "wake.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return WakePolicy.load(path)

    def test_missing_file_gives_defaults(self):
        self.assertEqual(WakePolicy.load("/nonexistent/wake.json"), WakePolicy())

    def test_reads_the_fields(self):
        policy = self.load({"min_frames": 90, "max_per_match": 5})
        self.assertEqual(policy.min_frames, 90)
        self.assertEqual(policy.max_per_match, 5)

    def test_unknown_keys_are_rejected(self):
        # 认不出的键要报错，静默忽略会让人以为配置生效了
        with self.assertRaises(ValueError):
            self.load({"min_frame": 90})


if __name__ == "__main__":
    unittest.main()


class TestRealLoopback(unittest.TestCase):
    """真起一个本地 HTTP 服务走一遍——假投递绕过了 `urllib` 那一段。"""

    def setUp(self):
        import http.server
        import threading

        received = self.received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                received.append((self.path, json.loads(body)))
                payload = json.dumps({"ok": True, "session": "s1"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/ra2/wake"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_round_trip(self):
        bridge = WakeBridge(endpoint=self.endpoint, policy=WakePolicy())
        record = bridge.request("基地被打", frame=8120, tactic="watch_base")
        self.assertTrue(record["sent"], record.get("error"))
        self.assertIn("session", record["reply"])
        path, payload = self.received[0]
        self.assertEqual(path, "/ra2/wake")
        self.assertIn("基地被打", payload["text"])
        self.assertEqual(payload["frame"], 8120)

    def test_unreachable_endpoint_reports_the_reason(self):
        bridge = WakeBridge(endpoint="http://127.0.0.1:1/ra2/wake",
                            policy=WakePolicy(timeout=0.5))
        record = bridge.request("基地被打", frame=1)
        self.assertFalse(record["sent"])
        self.assertTrue(record["error"])
