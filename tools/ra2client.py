#!/usr/bin/env python3
"""ra2yrcpp 客户端：protobuf 编解码、状态解析、发送前校验。

手写 protobuf 与 WebSocket 编解码，只用标准库，可在 WSL 下直接运行。
服务监听 Windows 侧 `127.0.0.1:14521`，WSL 镜像网络下 `127.0.0.1` 互通。

观测模型（据源码）：
- 每帧 `GetGameState` 返回 `objects`、`houses`、`factories`、`cells_difference` 与事件列表。
- **`GameState.map_data`从不填充**；完整地图只在 `StorageValue.map_data` 中，经 `ReadValue` 取一次。
- 地图变化随 `GameState.cells_difference` 增量送达，按 `Cell.index` 回填。

用法:
    python3 ra2client.py            # 连接并打印状态摘要
    python3 ra2client.py --map      # 另打印地图摘要
"""
import argparse
import sys
import time

from ra2ws import WebSocket, WebSocketError

# ---------------------------------------------------------------- 常量
CMD_NONE, CMD_SHUTDOWN, CMD_CLIENT, CMD_CLIENT_OLD, CMD_POLL, CMD_POLL_BLOCKING = 0, 1, 2, 3, 4, 5

NS = "ra2yrproto.commands."
NS_CORE = "ra2yrproto."

# UnitAction
UA_NONE, UA_DEPLOY, UA_SELECT, UA_UNSELECT, UA_TRY_TO_DEPLOY = 0, 1, 2, 3, 4
UA_SELL, UA_MOVE, UA_CAPTURE, UA_ATTACK, UA_REPAIR = 5, 6, 7, 8, 9
UA_STOP, UA_SELL_CELL, UA_ATTACK_MOVE = 10, 11, 12

# 源码 commands_game.cpp 的 switch 实际实现的动作
UA_IMPLEMENTED = {UA_DEPLOY, UA_SELECT, UA_SELL, UA_SELL_CELL, UA_MOVE,
                  UA_CAPTURE, UA_ATTACK, UA_ATTACK_MOVE, UA_STOP, UA_REPAIR}

MISSION_NAMES = {
    0: "Sleep", 1: "Attack", 2: "Move", 3: "QMove", 4: "Retreat", 5: "Guard",
    6: "Sticky", 7: "Enter", 8: "Capture", 9: "Eaten", 10: "Harvest",
    11: "AreaGuard", 12: "Return", 13: "Stop", 14: "Ambush", 15: "Hunt",
    16: "Unload", 17: "Sabotage", 18: "Construction", 19: "Selling",
    20: "Repair", 21: "Rescue", 22: "Missile", 23: "Harmless", 24: "Open",
    25: "Patrol", 26: "ParadropApproach", 27: "ParadropOverfly", 28: "Wait",
    29: "AttackMove", 30: "SpyplaneApproach", 31: "SpyplaneOverfly",
}

LEPTONS_PER_CELL = 256


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


def pb_int(field, v):
    """int32 负数按补码编码为 64 位 varint。"""
    return pb_uint(field, v & 0xFFFFFFFFFFFFFFFF if v < 0 else v)


def any_pack(type_name, payload):
    """google.protobuf.Any { 1: type_url, 2: value }"""
    return pb_str(1, "type.googleapis.com/" + type_name) + pb_bytes(2, payload)


def make_command(cmd_type, type_name, payload=b"", blocking=False):
    """Command { 1: command_type, 3: Any, 4: blocking }"""
    out = pb_uint(1, cmd_type) + pb_bytes(3, any_pack(type_name, payload))
    if blocking:
        out += pb_uint(4, 1)
    return out


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
    """逐条产出 (field_no, wire_type, value)。packed repeated 作为 bytes 返回。"""
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


def fmap(msg):
    """把一条消息按字段号聚成 dict；重复字段归入 list。"""
    out = {}
    for f, wt, v in fields(msg):
        out.setdefault(f, []).append((wt, v))
    return out


def one(msg, field, default=None):
    """取单值字段。"""
    got = fmap(msg).get(field)
    return got[0][1] if got else default


def sub(msg, field):
    """取嵌套消息的字节。"""
    return one(msg, field, b"")


def packed_varints(blob):
    """解 packed repeated varint。"""
    out, p = [], 0
    while p < len(blob):
        v, p = rv(blob, p)
        out.append(v)
    return out


def zigzag(v):
    """protobuf sint32/sint64 解码。"""
    return (v >> 1) ^ -(v & 1)


def any_unpack(blob):
    """返回 (type_name, payload)。"""
    tn, val = "", b""
    for f, wt, v in fields(blob):
        if f == 1 and wt == 2:
            tn = v.decode()
        elif f == 2 and wt == 2:
            val = v
    if tn.startswith("type.googleapis.com/"):
        tn = tn[len("type.googleapis.com/"):]
    return tn, val


# ---------------------------------------------------------------- 状态解析
def parse_coordinates(blob):
    m = fmap(blob)
    return {
        "x": m.get(1, [(0, 0)])[0][1],
        "y": m.get(2, [(0, 0)])[0][1],
        "z": m.get(3, [(0, 0)])[0][1],
    }


def parse_object(blob):
    m = fmap(blob)
    g = lambda f, d=0: m.get(f, [(0, d)])[0][1]  # noqa: E731
    return {
        "type_class": g(1),
        "health": g(2),
        "coordinates": parse_coordinates(sub(blob, 3)),
        "house": g(4),
        "array_index": g(8),
        "object_type": g(9),
        "self": g(10),
        "initial_owner": g(11),
        "selected": bool(g(13)),
        "deployed": bool(g(14)),
        "deploying": bool(g(15)),
        "undeploying": bool(g(16)),
        "destination": parse_coordinates(sub(blob, 17)),
        "mission": g(18),
        "in_limbo": bool(g(19)),
        "on_map": bool(g(20)),
    }


def parse_house(blob):
    m = fmap(blob)
    g = lambda f, d=0: m.get(f, [(0, d)])[0][1]  # noqa: E731
    name = g(2, b"")
    faction = g(3, b"")
    return {
        "array_index": g(1),
        "name": name.decode(errors="replace") if isinstance(name, bytes) else name,
        "faction": faction.decode(errors="replace") if isinstance(faction, bytes) else faction,
        "defeated": bool(g(4)),
        "current_player": bool(g(5)),
        "money": g(7),
        "self": g(8),
    }


class GameState:
    """一帧观测。`objects` 与 `houses` 已解析为字典。"""

    def __init__(self, payload):
        self.raw = payload
        m = fmap(payload)
        self.frame = m.get(1, [(0, 0)])[0][1]
        self.stage = m.get(7, [(0, 0)])[0][1]
        self.tech_level = m.get(14, [(0, 0)])[0][1]
        self.crc = m.get(16, [(0, 0)])[0][1]
        self.houses = [parse_house(v) for _, v in m.get(4, [])]
        self.objects = [parse_object(v) for _, v in m.get(6, [])]
        self.object_types = [v for _, v in m.get(5, [])]
        self.factories = [v for _, v in m.get(3, [])]
        self.cells_difference = [v for _, v in m.get(15, [])]
        self._by_pointer = {o["self"]: o for o in self.objects}

    def object(self, pointer):
        return self._by_pointer.get(pointer)

    def player_house(self):
        for h in self.houses:
            if h["current_player"]:
                return h
        return None

    def own_objects(self):
        h = self.player_house()
        if h is None:
            return []
        return [o for o in self.objects if o["house"] == h["self"]]

    def summary(self):
        h = self.player_house()
        return (f"frame={self.frame} stage={self.stage} "
                f"objects={len(self.objects)} houses={len(self.houses)} "
                f"cellsDiff={len(self.cells_difference)} "
                f"player={h['name'] if h else '?'} money={h['money'] if h else '?'}")


class MapData:
    """`ReadValue{map_data_soa}` 的结果，静态地图以结构数组形式返回。"""

    FIELDS = {1: "land_type", 2: "radiation_level", 3: "height", 4: "level",
              5: "overlay_data", 6: "tiberium_value", 7: "shrouded",
              8: "passability"}

    def __init__(self, payload):
        storage = sub(payload, 1)          # StorageValue
        soa = sub(storage, 5)              # map_data_soa
        self.raw = soa
        m = fmap(soa)
        self.width = m.get(9, [(0, 0)])[0][1]
        self.height = m.get(10, [(0, 0)])[0][1]
        self.columns = {}
        for f, name in self.FIELDS.items():
            entries = m.get(f, [])
            values = []
            for wt, v in entries:
                if wt == 0:
                    values.append(v)
                elif wt == 2:
                    values.extend(packed_varints(v))
            self.columns[name] = values

    def cell_index(self, cx, cy):
        return cy * self.width + cx

    def shrouded(self, cx, cy):
        i = self.cell_index(cx, cy)
        col = self.columns.get("shrouded", [])
        return bool(col[i]) if i < len(col) else True

    def summary(self):
        n = len(self.columns.get("shrouded", []))
        known = sum(1 for v in self.columns.get("shrouded", []) if not v)
        return (f"map={self.width}x{self.height} cells={n} "
                f"explored={known} ({100.0 * known / n:.1f}%)" if n else
                f"map={self.width}x{self.height} cells=0")


# ---------------------------------------------------------------- 校验
class InvalidCommand(ValueError):
    """命令在本地被拒绝：继续发送会崩溃游戏或必然失败。"""


class Validator:
    """发送前校验。规则见 .agents/notes/命令接口源码结论.md#前置校验清单。"""

    def __init__(self, map_data=None):
        self.width = map_data.width if map_data else None
        self.height = map_data.height if map_data else None

    def cell_of(self, x, y):
        """复现 CellClass::Coord2Cell：除以 256 后截断为 short。

        截断为 short 意味着越界坐标会回绕成看似合法的格子，因此不能只检查
        回绕后的结果。
        """
        return self._trunc_div(x, LEPTONS_PER_CELL), self._trunc_div(y, LEPTONS_PER_CELL)

    @staticmethod
    def _trunc_div(a, b):
        """C++ 整数除法向零截断。"""
        q = abs(a) // abs(b)
        return -q if (a < 0) != (b < 0) else q

    def check_coordinates(self, x, y):
        """坐标须使所落格子在地图内，且不触发 short 回绕。"""
        if self.width is None:
            raise InvalidCommand("尚未读取地图，无法校验坐标")
        cx, cy = self.cell_of(x, y)
        if not (0 <= x < self.width * LEPTONS_PER_CELL):
            raise InvalidCommand(
                f"x={x} 越界，合法范围 [0, {self.width * LEPTONS_PER_CELL})")
        if not (0 <= y < self.height * LEPTONS_PER_CELL):
            raise InvalidCommand(
                f"y={y} 越界，合法范围 [0, {self.height * LEPTONS_PER_CELL})")
        if not (0 <= cx < self.width and 0 <= cy < self.height):
            raise InvalidCommand(f"({x},{y}) 落到格 ({cx},{cy})，超出地图")

    def check_state(self, state):
        if not isinstance(state, GameState):
            raise InvalidCommand("需要一帧 GameState 才能校验")

    def check_objects(self, state, addresses):
        if not addresses:
            raise InvalidCommand("object_addresses 为空")
        for a in addresses:
            o = state.object(a)
            if o is None:
                raise InvalidCommand(f"对象 {a} 不在当前状态中")
            if o["in_limbo"]:
                raise InvalidCommand(f"对象 {a} 处于 limbo")

    def check_mission(self, state, addresses):
        """Mission_None 与 Mission_Construction 会被服务端拒绝。"""
        for a in addresses:
            o = state.object(a)
            if o is None:
                continue
            # Mission_None 在 proto 中为 -1，线路上按补码编码
            if o["mission"] in (-1, 0xFFFFFFFFFFFFFFFF, 18):
                raise InvalidCommand(
                    f"对象 {a} 的 mission={o['mission']} 非法，服务端会拒绝")

    def check_action(self, action):
        if action not in UA_IMPLEMENTED:
            raise InvalidCommand(
                f"action={action} 未实现，服务端会抛 invalid unit action")

    def check_unit_order(self, state, addresses, action, target_object=0,
                         coordinates=None):
        self.check_state(state)
        if action == UA_SELL_CELL:
            if coordinates is None:
                raise InvalidCommand("SELL_CELL 需要 coordinates")
            self.check_coordinates(coordinates[0], coordinates[1])
            return
        self.check_action(action)
        self.check_objects(state, addresses)
        self.check_mission(state, addresses)
        if action in (UA_CAPTURE, UA_ATTACK, UA_REPAIR) and not target_object:
            raise InvalidCommand(f"action={action} 需要 target_object")
        if action in (UA_MOVE, UA_ATTACK_MOVE):
            if coordinates is None:
                raise InvalidCommand(f"action={action} 需要 coordinates")
            self.check_coordinates(coordinates[0], coordinates[1])


# ---------------------------------------------------------------- 客户端
class Client:
    def __init__(self, host="127.0.0.1", port=14521, timeout=10):
        self.host, self.port, self.timeout = host, port, timeout
        self.ws = None
        self.queue_id = None
        self.validator = Validator()

    def connect(self):
        self.ws = WebSocket(self.host, self.port, timeout=self.timeout)
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

    def request(self, cmd_type, type_name, payload=b"", blocking=False):
        """发一帧命令，读一帧响应，返回 Response.body 的 Any 原始字节。"""
        self.ws.send_binary(make_command(cmd_type, type_name, payload, blocking))
        raw = self.ws.recv()
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

    def _poll_for(self, command_id, poll_timeout_ms):
        """轮询直到取回指定 id 的结果；结果可能分多批到达。"""
        deadline = time.time() + poll_timeout_ms / 1000.0
        while time.time() < deadline:
            args = pb_uint(1, self.queue_id) + pb_uint(2, 500)
            try:
                presp = self.request(CMD_POLL_BLOCKING, NS + "PollResults",
                                     pb_bytes(1, args))
            except (WebSocketError, OSError):
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
                    if cid == command_id:
                        rtn, rpl = any_unpack(rbody)
                        return {"type": rtn, "payload": rpl, "code": rcode,
                                "error": rerr}
        # 超时不视为失败：命令可能已执行，仅结果未送达
        return {"type": "POLL_TIMEOUT", "payload": b"", "code": None,
                "error": "poll timeout"}

    def send_command(self, type_name, payload=b"", poll_timeout=5000):
        """发命令并取回其结果。"""
        resp = self.request(CMD_CLIENT, type_name, payload)
        tn, pl = any_unpack(resp)
        ack = {}
        for f, wt, v in fields(pl):
            if f == 1 and wt == 0:
                ack["id"] = v
            elif f == 2 and wt == 0:
                ack["queue_id"] = v
        if "id" not in ack:
            raise RuntimeError(f"未取得命令 id（返回类型 {tn}）: {pl[:200]!r}")
        return self._poll_for(ack["id"], poll_timeout)

    # -------------------------------------------------------- 读
    def get_state(self, poll_timeout=5000):
        r = self.send_command(NS + "GetGameState", b"", poll_timeout)
        if r["type"] == "POLL_TIMEOUT":
            raise TimeoutError("GetGameState 超时；游戏是否失焦暂停？")
        return GameState(sub(r["payload"], 1))   # GetGameState{ state }

    def read_map(self, poll_timeout=15000):
        """地图只在 StorageValue 中，取一次即可；之后靠 cells_difference 增量更新。"""
        payload = pb_bytes(1, pb_bytes(5, b""))   # ReadValue{ data{ map_data_soa{} } }
        r = self.send_command(NS + "ReadValue", payload, poll_timeout)
        if r["type"] == "POLL_TIMEOUT":
            raise TimeoutError("ReadValue 超时")
        if r["code"]:
            raise RuntimeError(f"ReadValue 失败: {r['error']}")
        return MapData(r["payload"])

    def inspect_config(self, poll_timeout=5000):
        r = self.send_command(NS + "InspectConfiguration", b"", poll_timeout)
        return self._parse_config(sub(r["payload"], 1))

    @staticmethod
    def _parse_config(blob):
        m = fmap(blob)
        g = lambda f, d=0: m.get(f, [(0, d)])[0][1]  # noqa: E731
        s = lambda f: g(f, b"").decode(errors="replace")  # noqa: E731
        return {
            "debug_log": bool(g(1)),
            "record_filename": s(2),
            "traffic_filename": s(3),
            "parse_map_data_interval": g(4),
            "single_step": bool(g(5)),
            "port": g(6),
            "max_connections": g(7),
            "allowed_hosts_regex": s(8),
            "log_filename": s(9),
        }

    def update_config(self, parse_map_data_interval=None, single_step=None,
                      poll_timeout=5000):
        """运行时改写配置。

        `MainData::update_config` 只应用 `parse_map_data_interval`(>0 时) 与
        `single_step` 两个字段，其余字段不生效；`ConfigData::parse` 会把 0 强制
        改回 1，故无法用 0 关闭地图解析，只能给一个很大的值。
        """
        cfg = b""
        if parse_map_data_interval is not None:
            cfg += pb_uint(4, parse_map_data_interval)
        if single_step is not None:
            cfg += pb_uint(5, 1 if single_step else 0)
        payload = pb_bytes(1, cfg) + pb_uint(2, 1)   # InspectConfiguration{config, update=1}
        r = self.send_command(NS + "InspectConfiguration", payload, poll_timeout)
        if r["code"]:
            raise RuntimeError(f"更新配置失败: {r['error']}")
        return self._parse_config(sub(r["payload"], 1))

    # -------------------------------------------------------- 写
    def unit_order(self, addresses, action, target_object=0, coordinates=None,
                   validate=True, state=None, poll_timeout=5000):
        if validate:
            if state is None:
                state = self.get_state()
            self.validator.check_unit_order(state, addresses, action,
                                            target_object, coordinates)
        payload = b"".join(pb_uint(1, a) for a in addresses) + pb_uint(2, action)
        if target_object:
            payload += pb_uint(3, target_object)
        if coordinates is not None:
            payload += pb_bytes(4, pb_uint(1, coordinates[0])
                                + pb_uint(2, coordinates[1])
                                + pb_uint(3, coordinates[2] if len(coordinates) > 2 else 0))
        return self.send_command(NS + "UnitOrder", payload, poll_timeout)

    def add_message(self, text, duration_frames=150, color=0, poll_timeout=5000):
        payload = pb_str(1, text) + pb_uint(2, duration_frames) + pb_uint(3, color)
        return self.send_command(NS + "AddMessage", payload, poll_timeout)

    def close(self):
        if self.ws:
            self.ws.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=14521)
    ap.add_argument("--map", action="store_true", help="另读取并打印地图摘要")
    ap.add_argument("--config", action="store_true", help="打印服务端配置")
    a = ap.parse_args()

    c = Client(a.host, a.port)
    try:
        ack = c.connect()
        print(f"连接成功  queue_id={c.queue_id}  ack={ack}", file=sys.stderr)
        st = c.get_state()
        print(st.summary())
        for o in st.own_objects()[:12]:
            print(f"  obj self={o['self']:>10} type={o['object_type']:>2} "
                  f"mission={MISSION_NAMES.get(o['mission'], o['mission']):<12} "
                  f"@({o['coordinates']['x']},{o['coordinates']['y']}) "
                  f"hp={o['health']} sel={o['selected']}")
        if a.map:
            md = c.read_map()
            print(md.summary())
            c.validator = Validator(md)
        if a.config:
            for k, v in c.inspect_config().items():
                print(f"  {k} = {v!r}")
    finally:
        c.close()


if __name__ == "__main__":
    main()
