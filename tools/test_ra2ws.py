#!/usr/bin/env python3
"""ra2ws 的自测：用最小服务端验证握手、掩码、长度编码与分片重组。

不依赖游戏，`python3 test_ra2ws.py` 即可运行。
"""
import base64
import hashlib
import socket
import struct
import threading

from ra2ws import GUID, WebSocket, OP_BIN, OP_PING, OP_TEXT


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def read_frame(sock):
    """读取一个客户端帧并解掩码。"""
    b0, b1 = _recv_exact(sock, 2)
    fin = bool(b0 & 0x80)
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(sock, 8))[0]
    mask = _recv_exact(sock, 4) if masked else None
    payload = _recv_exact(sock, length) if length else b""
    if mask:
        payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
    return fin, opcode, payload


def send_frame(sock, opcode, payload, fin=True):
    """服务端发出的帧不掩码。"""
    n = len(payload)
    head = bytearray([(0x80 if fin else 0) | opcode])
    if n < 126:
        head.append(n)
    elif n < 65536:
        head.append(126)
        head += struct.pack(">H", n)
    else:
        head.append(127)
        head += struct.pack(">Q", n)
    sock.sendall(bytes(head) + payload)


class Server(threading.Thread):
    """按脚本应答的测试服务端。脚本项为 (opcode, payload) 或 ('frag', a, b)。"""

    def __init__(self, script):
        super().__init__(daemon=True)
        self.script = script
        self.received = []
        self.accept_ok = False
        self.port = 0
        self._ls = socket.socket()
        self._ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._ls.bind(("127.0.0.1", 0))
        self._ls.listen(1)
        self.port = self._ls.getsockname()[1]

    def run(self):
        conn, _ = self._ls.accept()
        try:
            req = b""
            while b"\r\n\r\n" not in req:
                req += conn.recv(4096)
            key = ""
            for line in req.decode("latin1").split("\r\n"):
                name, _, value = line.partition(":")
                if name.strip().lower() == "sec-websocket-key":
                    key = value.strip()
            accept = base64.b64encode(
                hashlib.sha1((key + GUID).encode()).digest()).decode()
            self.accept_ok = bool(key)
            conn.sendall((
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept}\r\n\r\n").encode())

            for item in self.script:
                if item[0] == "frag":
                    _, a, b = item
                    send_frame(conn, OP_BIN, a, fin=False)
                    send_frame(conn, 0x0, b, fin=True)
                elif item[0] == "expect":
                    self.received.append(read_frame(conn))
                else:
                    opcode, payload = item
                    send_frame(conn, opcode, payload)
        except (ConnectionError, OSError):
            pass
        finally:
            conn.close()
            self._ls.close()


def run_case(name, script, action):
    srv = Server(script)
    srv.start()
    ws = WebSocket("127.0.0.1", srv.port, timeout=5.0)
    try:
        ok = action(ws, srv)
    finally:
        ws.close()
    srv.join(timeout=2)
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return bool(ok)


def main():
    results = []

    def small(ws, srv):
        return ws.recv() == b"hello"

    results.append(run_case("小载荷二进制帧", [(OP_BIN, b"hello")], small))

    def medium(ws, srv):
        return ws.recv() == bytes(range(200))

    results.append(run_case("16 位长度帧(200B)",
                            [(OP_BIN, bytes(range(200)))], medium))

    def large(ws, srv):
        return ws.recv() == b"x" * 70000

    results.append(run_case("64 位长度帧(70000B)",
                            [(OP_BIN, b"x" * 70000)], large))

    def fragmented(ws, srv):
        return ws.recv() == b"abc" + b"def"

    results.append(run_case("分片消息重组", [("frag", b"abc", b"def")],
                            fragmented))

    def ping(ws, srv):
        # 服务端先发 ping，客户端在 recv 内应答 pong，服务端读到 pong 后才发数据。
        # 断言：ping 不被交给上层，且客户端确实回了 pong。
        data = ws.recv()
        return (data == b"payload" and bool(srv.received)
                and srv.received[-1][1] == 0xA)

    results.append(run_case("ping 自动应答 pong",
                            [(OP_PING, b""), ("expect",), (OP_BIN, b"payload")],
                            ping))

    def text(ws, srv):
        return ws.recv() == b"text-frame"

    results.append(run_case("文本帧", [(OP_TEXT, b"text-frame")], text))

    print(f"\n{sum(results)}/{len(results)} 通过")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
