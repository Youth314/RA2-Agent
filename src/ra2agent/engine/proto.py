"""protobuf 的最小编解码。

不依赖 protoc 生成的代码与 `google.protobuf` 运行时：本层只需读写固定字段，
手写比引入代码生成链更省事。字段号取自 `proto/ra2yrproto/`。
"""
from ..errors import ProtocolError

# ---------------------------------------------------------------- 编码
def varint(value):
    """把非负整数编码为 varint。"""
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def tag(field, wire):
    """编码字段号与线类型。"""
    return varint((field << 3) | wire)


def pb_uint(field, value):
    """编码 varint 字段。负数按补码作为 64 位无符号数处理。"""
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF
    return tag(field, 0) + varint(value)


def pb_bytes(field, data):
    """编码 length-delimited 字段。"""
    return tag(field, 2) + varint(len(data)) + data


def pb_str(field, text):
    """编码字符串字段。"""
    return pb_bytes(field, text.encode())


def any_pack(type_name, payload):
    """打包成 `google.protobuf.Any`。"""
    return pb_str(1, "type.googleapis.com/" + type_name) + pb_bytes(2, payload)


def make_command(command_type, type_name, payload=b"", blocking=False):
    """构造 `Command{1: command_type, 3: Any, 4: blocking}`。"""
    out = pb_uint(1, command_type) + pb_bytes(3, any_pack(type_name, payload))
    if blocking:
        out += pb_uint(4, 1)
    return out


# ---------------------------------------------------------------- 解码
def _read_varint(buf, pos):
    result, shift = 0, 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def fields(message):
    """逐条产出 `(field_no, wire_type, value)`。

    length-delimited 字段的值是 `bytes`，varint 字段是 `int`，定长字段是原始
    字节。服务端把 repeated 标量按 packed 编码，故调用方可能拿到 `bytes` 而非
    `int`，需要 `packed_varints` 解开。
    """
    pos = 0
    end = len(message)
    while pos < end:
        key, pos = _read_varint(message, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _read_varint(message, pos)
        elif wire == 2:
            length, pos = _read_varint(message, pos)
            value = message[pos:pos + length]
            pos += length
        elif wire == 5:
            value = message[pos:pos + 4]
            pos += 4
        elif wire == 1:
            value = message[pos:pos + 8]
            pos += 8
        else:
            raise ProtocolError(f"不支持的线类型 {wire}（字段 {field}）")
        yield field, wire, value


def fmap(message):
    """把一条消息按字段号聚成 `{字段号: [(线类型, 值)]}`。"""
    out = {}
    for field, wire, value in fields(message):
        out.setdefault(field, []).append((wire, value))
    return out


def one(message, field, default=None):
    """取单值字段。"""
    got = fmap(message).get(field)
    return got[0][1] if got else default


def sub(message, field, default=b""):
    """取嵌套消息的字节。"""
    return one(message, field, default)


def packed_varints(blob):
    """解开 packed repeated varint。"""
    out, pos = [], 0
    while pos < len(blob):
        value, pos = _read_varint(blob, pos)
        out.append(value)
    return out


def repeated_ints(entries):
    """把某字段的全部取值摊平为整数列表，兼容 packed 与逐个编码。"""
    out = []
    for wire, value in entries:
        if wire == 0:
            out.append(value)
        elif wire == 2:
            out.extend(packed_varints(value))
    return out


def signed64(value):
    """把按补码编码的 64 位无符号数还原为有符号整数。"""
    return value - (1 << 64) if value >= (1 << 63) else value


def any_unpack(blob):
    """解开 `google.protobuf.Any`，返回 `(类型名, 载荷)`。"""
    type_name, payload = "", b""
    for field, wire, value in fields(blob):
        if field == 1 and wire == 2:
            type_name = value.decode()
        elif field == 2 and wire == 2:
            payload = value
    prefix = "type.googleapis.com/"
    if type_name.startswith(prefix):
        type_name = type_name[len(prefix):]
    return type_name, payload
