"""WebSocket 帧编解码的测试。

用最小服务端验证握手、掩码、长度编码与分片重组。服务端实现只求正确，不求通用。
"""
import base64
import hashlib
import socket
import struct
import threading
import unittest

from ra2agent.errors import ProtocolError
from ra2agent.engine.wire import OP_BIN, OP_PING, OP_TEXT, WebSocket

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _recv_exact(sock, count):
    buf = b""
    while len(buf) < count:
        chunk = sock.recv(count - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def read_frame(sock):
    """读取一个客户端帧并解掩码，返回 `(final, opcode, payload)`。"""
    first, second = _recv_exact(sock, 2)
    final = bool(first & 0x80)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else None
    payload = _recv_exact(sock, length) if length else b""
    if mask:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    return final, opcode, payload


def send_frame(sock, opcode, payload, final=True):
    """服务端发出的帧不掩码。"""
    length = len(payload)
    head = bytearray([(0x80 if final else 0) | opcode])
    if length < 126:
        head.append(length)
    elif length < 65536:
        head.append(126)
        head += struct.pack(">H", length)
    else:
        head.append(127)
        head += struct.pack(">Q", length)
    sock.sendall(bytes(head) + payload)


class FakeServer(threading.Thread):
    """按脚本应答的测试服务端。

    脚本项为 `(opcode, payload)`、`("frag", a, b)` 或 `("expect",)`（读取一个
    客户端帧存入 `received`）。
    """

    def __init__(self, script, accept_override=None):
        super().__init__(daemon=True)
        self.script = script
        self.accept_override = accept_override
        self.received = []
        self.handshake_ok = False
        self.error = None
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]

    def run(self):
        conn, _ = self._listener.accept()
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            key = ""
            for line in request.decode("latin1").split("\r\n"):
                name, _, value = line.partition(":")
                if name.strip().lower() == "sec-websocket-key":
                    key = value.strip()
            accept = self.accept_override or base64.b64encode(
                hashlib.sha1((key + _GUID).encode()).digest()).decode()
            self.handshake_ok = bool(key)
            conn.sendall((
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())
            for item in self.script:
                if item[0] == "frag":
                    _, first, second = item
                    send_frame(conn, OP_BIN, first, final=False)
                    send_frame(conn, 0x0, second, final=True)
                elif item[0] == "expect":
                    self.received.append(read_frame(conn))
                else:
                    opcode, payload = item
                    send_frame(conn, opcode, payload)
        except (ConnectionError, OSError) as exc:
            self.error = exc
        finally:
            conn.close()
            self._listener.close()


def with_server(script, action, accept_override=None):
    """起一个服务端，跑 action，返回 `(结果, 服务端)`。"""
    server = FakeServer(script, accept_override)
    server.start()
    client = WebSocket("127.0.0.1", server.port, timeout=5.0)
    try:
        result = action(client, server)
    finally:
        client.close()
    server.join(timeout=2)
    return result, server


class TestFraming(unittest.TestCase):
    def test_small_binary(self):
        result, _ = with_server([(OP_BIN, b"hello")], lambda c, s: c.recv())
        self.assertEqual(result, b"hello")

    def test_16bit_length(self):
        payload = bytes(range(200))
        result, _ = with_server([(OP_BIN, payload)], lambda c, s: c.recv())
        self.assertEqual(result, payload)

    def test_64bit_length(self):
        payload = b"x" * 70000
        result, _ = with_server([(OP_BIN, payload)], lambda c, s: c.recv())
        self.assertEqual(result, payload)

    def test_text_frame(self):
        result, _ = with_server([(OP_TEXT, b"text")], lambda c, s: c.recv())
        self.assertEqual(result, b"text")

    def test_fragmented_message_reassembled(self):
        result, _ = with_server([("frag", b"abc", b"def")],
                                lambda c, s: c.recv())
        self.assertEqual(result, b"abcdef")

    def test_client_masks_its_frames(self):
        def action(client, server):
            client.send_binary(b"ping")
            return None
        _, server = with_server([("expect",)], action)
        final, opcode, payload = server.received[0]
        self.assertEqual((final, opcode, payload), (True, OP_BIN, b"ping"))

    def test_ping_is_answered_and_not_delivered(self):
        # 服务端先发 ping，收到 pong 后才发数据
        def action(client, server):
            return client.recv()
        result, server = with_server(
            [(OP_PING, b""), ("expect",), (OP_BIN, b"payload")], action)
        self.assertEqual(result, b"payload")
        self.assertEqual(server.received[-1][1], 0xA)


class TestHandshake(unittest.TestCase):
    def test_good_handshake(self):
        def action(client, server):
            return client.recv()
        result, server = with_server([(OP_BIN, b"ok")], action)
        self.assertEqual(result, b"ok")
        self.assertTrue(server.handshake_ok)

    def test_rejects_bad_accept(self):
        with self.assertRaises(ProtocolError):
            with_server([], lambda c, s: c.recv(),
                        accept_override="wrong-value")

    def test_rejects_connection_closed_during_handshake(self):
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def drop():
            conn, _ = listener.accept()
            conn.close()
            listener.close()

        threading.Thread(target=drop, daemon=True).start()
        with self.assertRaises(ProtocolError):
            WebSocket("127.0.0.1", port, timeout=5.0)


if __name__ == "__main__":
    unittest.main()
