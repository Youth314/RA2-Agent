"""最小 WebSocket 客户端（RFC 6455），只用标准库。

只实现本项目需要的部分：文本与二进制帧、分片重组、ping/pong 应答。
不实现扩展协商，故不请求 permessage-deflate。
"""
import base64
import hashlib
import os
import socket
import struct

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BIN = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA


class WebSocketError(Exception):
    """连接建立失败、连接中断或协议违例。"""


class WebSocket:
    """同步 WebSocket 客户端。

    一次 `recv` 返回一条完整消息（分片已重组），`send_binary` 发送一条消息。
    """

    def __init__(self, host, port, timeout=10.0, path="/"):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._buf = b""
        self._frag = bytearray()
        self._handshake(host, port, path)

    # ------------------------------------------------------------------ 握手
    def _handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(req.encode())

        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WebSocketError("握手期间连接关闭")
            head += chunk
        raw_header, _, rest = head.partition(b"\r\n\r\n")
        self._buf = rest

        lines = raw_header.decode("latin1").split("\r\n")
        if " 101" not in lines[0]:
            raise WebSocketError(f"握手失败: {lines[0]}")

        accept = None
        for line in lines[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "sec-websocket-accept":
                accept = value.strip()
        expect = base64.b64encode(
            hashlib.sha1((key + GUID).encode()).digest()).decode()
        if accept != expect:
            raise WebSocketError(f"Sec-WebSocket-Accept 不匹配: {accept!r}")

    # -------------------------------------------------------------- 字节读取
    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(max(4096, n - len(self._buf)))
            if not chunk:
                raise WebSocketError("连接关闭")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def _read_frame(self):
        b0, b1 = self._recv_exact(2)
        fin = bool(b0 & 0x80)
        opcode = b0 & 0x0F
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length) if length else b""
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return fin, opcode, payload

    # -------------------------------------------------------------- 收发消息
    def _send_frame(self, opcode, payload):
        """客户端发出的帧必须掩码。"""
        n = len(payload)
        head = bytearray([0x80 | opcode])
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(bytes(head)
                          + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def send_binary(self, data):
        self._send_frame(OP_BIN, data)

    def recv(self):
        """返回下一条完整消息的字节，处理控制帧与分片。"""
        while True:
            fin, opcode, payload = self._read_frame()
            if opcode == OP_CLOSE:
                raise WebSocketError("服务端发送关闭帧")
            if opcode == OP_PING:
                self._send_frame(OP_PONG, payload)
                continue
            if opcode == OP_PONG:
                continue
            if opcode in (OP_TEXT, OP_BIN):
                self._frag = bytearray(payload)
            elif opcode == OP_CONT:
                self._frag += payload
            else:
                continue
            if fin:
                data = bytes(self._frag)
                self._frag = bytearray()
                return data

    def close(self):
        try:
            self._send_frame(OP_CLOSE, b"")
        except OSError:
            pass
        finally:
            self.sock.close()
