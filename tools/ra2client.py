#!/usr/bin/env python3
"""ra2yrcpp 的最小客户端，用于验证命令通道。

手写 protobuf 编解码，不依赖 protoc 生成代码。
仅在 Windows Python 下运行（服务绑定在 Windows 的 0.0.0.0:14521）。

用法:
    python ra2client.py                       # 连接并读 GetSystemState
    python ra2client.py --cmd GetGameState    # 读完整游戏状态（输出体积大）
"""
import argparse
import json
import sys
import time

import websocket

# ---------------------------------------------------------------- protobuf 编码
def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _tag(field, wire):
    return _varint((field << 3) | wire)


def pb_bytes(field, data):
    return _tag(field, 2) + _varint(len(data)) + data


def pb_str(field, s):
    return pb_bytes(field, s.encode())


def pb_uint(field, v):
    return _tag(field, 0) + _varint(v)


def any_pack(type_name, payload):
    """google.protobuf.Any { 1: type_url, 2: value }"""
    return pb_str(1, "type.googleapis.com/" + type_name) + pb_bytes(2, payload)


def make_command(cmd_type, type_name, payload=b""):
    """Command { 1: command_type, 3: Any }"""
    return pb_uint(1, cmd_type) + pb_bytes(3, any_pack(type_name, payload))


# ---------------------------------------------------------------- protobuf 解码
def rv(b, i):
    r = 0
    s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        if not (x & 0x80):
            break
        s += 7
    return r, i


def fields(msg):
    """Yield (field_no, wire_type, value) for one protobuf message."""
    p = 0
    while p < len(msg):
        key, p = rv(msg, p)
        f, wt = key >> 3, key & 7
        if wt == 0:
            v, p = rv(msg, p)
            yield f, wt, v
        elif wt == 2:
            ln, p = rv(msg, p)
            yield f, wt, msg[p:p + ln]
            p += ln
        elif wt == 5:
            yield f, wt, msg[p:p + 4]
            p += 4
        elif wt == 1:
            yield f, wt, msg[p:p + 8]
            p += 8
        else:
            return


def any_unpack(blob):
    """Return (type_name, payload)."""
    tn, val = "", b""
    for f, wt, v in fields(blob):
        if f == 1 and wt == 2:
            tn = v.decode()
        elif f == 2 and wt == 2:
            val = v
    if tn.startswith("type.googleapis.com/"):
        tn = tn[len("type.googleapis.com/"):]
    return tn, val


# ---------------------------------------------------------------- 客户端
CMD_NONE, CMD_SHUTDOWN, CMD_CLIENT, CMD_CLIENT_OLD, CMD_POLL, CMD_POLL_BLOCKING = 0, 1, 2, 3, 4, 5

NS = "ra2yrproto.commands."
NS_CORE = "ra2yrproto."


class Client:
    def __init__(self, host, port, timeout=10):
        self.url = f"ws://{host}:{port}"
        self.timeout = timeout
        self.ws = None
        self.queue_id = None

    def connect(self):
        self.ws = websocket.create_connection(self.url, timeout=self.timeout)
        # 握手：发 GetSystemState，取回 queue_id
        resp = self.request(CMD_CLIENT, NS + "GetSystemState")
        tn, payload = any_unpack(resp)
        ack = {}
        for f, wt, v in fields(payload):
            if f == 1 and wt == 0:
                ack["id"] = v
            elif f == 2 and wt == 0:
                ack["queue_id"] = v
        if "queue_id" not in ack:
            raise RuntimeError(f"握手失败，未取得 queue_id（返回类型 {tn}）")
        self.queue_id = ack["queue_id"]
        return ack

    def request(self, cmd_type, type_name, payload=b""):
        """发一帧命令，读一帧响应，返回 Response.body 的 Any 原始字节。"""
        self.ws.send_binary(make_command(cmd_type, type_name, payload))
        raw = self.ws.recv()
        if isinstance(raw, str):
            raw = raw.encode("latin1")
        code, body = None, b""
        for f, wt, v in fields(raw):
            if f == 1 and wt == 0:
                code = v
            elif f == 2 and wt == 2:
                body = v
        # proto3 不序列化默认值，code 缺席即表示 OK
        if code not in (None, 0):
            tn, pl = any_unpack(body)
            raise RuntimeError(f"server error code={code} type={tn} body={pl[:200]!r}")
        return body

    def send_command(self, type_name, payload=b"", poll_timeout=5000):
        """发命令并取回其结果。"""
        resp = self.request(CMD_CLIENT, type_name, payload)
        tn, pl = any_unpack(resp)
        ack = {}
        for f, wt, v in fields(pl):
            if f == 0:
                pass
            elif f == 1 and wt == 0:
                ack["id"] = v
            elif f == 2 and wt == 0:
                ack["queue_id"] = v
        if "id" not in ack:
            raise RuntimeError(f"未取得命令 id（返回类型 {tn}）: {pl[:200]!r}")

        # 轮询取结果：结果可能分批到达，需要循环
        deadline = time.time() + poll_timeout / 1000.0
        while time.time() < deadline:
            args = pb_uint(1, self.queue_id) + pb_uint(2, 500)
            poll_payload = pb_bytes(1, args)  # PollResults.args
            try:
                presp = self.request(CMD_POLL_BLOCKING, NS + "PollResults", poll_payload)
            except Exception:
                continue
            ptn, ppl = any_unpack(presp)
            for f, wt, v in fields(ppl):
                if f != 2 or wt != 2:
                    continue
                for rf, rwt, rv in fields(v):
                    if rf != 1 or rwt != 2:
                        continue
                    cid = rcode = None
                    rbody, rerr = b"", ""
                    for cf, cwt, cv in fields(rv):
                        if cf == 1 and cwt == 0:
                            cid = cv
                        elif cf == 2 and cwt == 2:
                            rbody = cv
                        elif cf == 3 and cwt == 0:
                            rcode = cv
                        elif cf == 4 and cwt == 2:
                            rerr = cv.decode(errors="replace")
                    if cid == ack["id"]:
                        rtn, rpl = any_unpack(rbody)
                        return {"type": rtn, "payload": rpl, "code": rcode, "error": rerr}
        # 超时不视为失败：命令可能已执行，仅结果未送达
        return {"type": "POLL_TIMEOUT", "payload": b"", "code": None, "error": "poll timeout"}

    def close(self):
        if self.ws:
            self.ws.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=14521)
    ap.add_argument("--cmd", default="GetSystemState")
    ap.add_argument("--raw", action="store_true", help="输出原始 payload 的十六进制")
    a = ap.parse_args()

    c = Client(a.host, a.port)
    try:
        ack = c.connect()
        print(f"连接成功  queue_id={c.queue_id}  ack={ack}", file=sys.stderr)
        r = c.send_command(NS + a.cmd)
        print(f"命令 {a.cmd} 返回类型: {r['type']}", file=sys.stderr)
        if a.raw:
            print(r["payload"].hex())
        else:
            print(f"payload 长度 {len(r['payload'])} 字节")
            print(r["payload"][:400].hex())
    finally:
        c.close()


if __name__ == "__main__":
    main()
