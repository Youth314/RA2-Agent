"""最小 WebSocket 客户端（RFC 6455），只用标准库。

只实现本项目所需：文本与二进制帧、分片重组、ping/pong 应答。不实现扩展协商，
故不请求 permessage-deflate。
"""
import base64
import hashlib
import os
import socket
import struct

from .errors import ProtocolError

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BIN = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA


class WebSocket:
    """同步 WebSocket 客户端。

    一次 `recv` 返回一条完整消息（分片已重组）；`send_binary` 发送一条消息。
    """

    def __init__(self, host, port, timeout=10.0, path="/"):
        try:
            self.sock = socket.create_connection((host, port), timeout=timeout)
        except OSError as exc:
            raise ProtocolError(f"无法连接 {host}:{port}：{exc}") from exc
        self.sock.settimeout(timeout)
        self._buf = b""
        self._frag = bytearray()
        try:
            self._handshake(host, port, path)
        except BaseException:
            self.sock.close()
            raise

    # ------------------------------------------------------------------ 握手
    def _handshake(self, host, port, path):
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode())

        head = b""
        while b"\r\n\r\n" not in head:
            try:
                chunk = self.sock.recv(4096)
            except OSError as exc:
                raise ProtocolError(f"握手期间连接中断：{exc}") from exc
            if not chunk:
                raise ProtocolError("握手期间连接关闭")
            head += chunk
        raw_header, _, rest = head.partition(b"\r\n\r\n")
        self._buf = rest

        lines = raw_header.decode("latin1").split("\r\n")
        if " 101" not in lines[0]:
            raise ProtocolError(f"握手失败: {lines[0]}")

        accept = None
        for line in lines[1:]:
            name, _, value = line.partition(":")
            if name.strip().lower() == "sec-websocket-accept":
                accept = value.strip()
        expected = base64.b64encode(
            hashlib.sha1((key + _GUID).encode()).digest()).decode()
        if accept != expected:
            raise ProtocolError(f"Sec-WebSocket-Accept 不匹配: {accept!r}")

    # -------------------------------------------------------------- 字节读取
    def _recv_exact(self, count):
        while len(self._buf) < count:
            try:
                chunk = self.sock.recv(max(4096, count - len(self._buf)))
            except OSError as exc:
                raise ProtocolError(f"连接中断：{exc}") from exc
            if not chunk:
                raise ProtocolError("连接关闭")
            self._buf += chunk
        out, self._buf = self._buf[:count], self._buf[count:]
        return out

    def _read_frame(self):
        first, second = self._recv_exact(2)
        final = bool(first & 0x80)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_exact(8))[0]
        mask = self._recv_exact(4) if masked else None
        payload = self._recv_exact(length) if length else b""
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return final, opcode, payload

    # -------------------------------------------------------------- 收发消息
    def _send_frame(self, opcode, payload):
        """客户端发出的帧必须掩码。"""
        length = len(payload)
        head = bytearray([0x80 | opcode])
        if length < 126:
            head.append(0x80 | length)
        elif length < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", length)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", length)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(
            bytes(head)
            + bytes(c ^ mask[i % 4] for i, c in enumerate(payload)))

    def send_binary(self, data):
        """发送一条二进制消息。"""
        self._send_frame(OP_BIN, data)

    def recv(self):
        """返回下一条完整消息，处理控制帧与分片。"""
        while True:
            final, opcode, payload = self._read_frame()
            if opcode == OP_CLOSE:
                raise ProtocolError("服务端发送关闭帧")
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
            if final:
                data = bytes(self._frag)
                self._frag = bytearray()
                return data

    def close(self):
        """发送关闭帧并关闭套接字。"""
        try:
            self._send_frame(OP_CLOSE, b"")
        except OSError:
            pass
        finally:
            self.sock.close()
