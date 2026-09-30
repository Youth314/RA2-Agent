"""protobuf 最小编解码的测试。"""
import unittest

from ra2agent.engine import proto
from ra2agent.errors import ProtocolError


class TestVarint(unittest.TestCase):
    def test_known_encodings(self):
        cases = [(0, b"\x00"), (1, b"\x01"), (127, b"\x7f"),
                 (128, b"\x80\x01"), (300, b"\xac\x02"),
                 (16384, b"\x80\x80\x01")]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(proto.varint(value), expected)

    def test_round_trip(self):
        for value in (0, 1, 127, 128, 300, 2 ** 31, 2 ** 63):
            with self.subTest(value=value):
                blob = proto.varint(value)
                decoded, pos = proto._read_varint(blob, 0)
                self.assertEqual(decoded, value)
                self.assertEqual(pos, len(blob))


class TestEncoding(unittest.TestCase):
    def test_tag(self):
        # 字段 1、线类型 0 -> (1<<3)|0 = 8
        self.assertEqual(proto.tag(1, 0), b"\x08")
        # 字段 4、线类型 0 -> (4<<3)|0 = 32
        self.assertEqual(proto.tag(4, 0), b"\x20")

    def test_pb_uint(self):
        self.assertEqual(proto.pb_uint(1, 2), b"\x08\x02")
        self.assertEqual(proto.pb_uint(2, 6), b"\x10\x06")

    def test_pb_uint_negative_is_twos_complement(self):
        # proto 的 int32 负数按 64 位补码编码
        encoded = proto.pb_uint(18, -1)
        tag_length = len(proto.tag(18, 0))
        self.assertEqual(encoded[:tag_length], proto.tag(18, 0))
        value, pos = proto._read_varint(encoded, tag_length)
        self.assertEqual(value, 2 ** 64 - 1)
        self.assertEqual(pos, len(encoded))

    def test_pb_bytes_and_str(self):
        self.assertEqual(proto.pb_bytes(2, b"ab"), b"\x12\x02ab")
        self.assertEqual(proto.pb_str(1, "hi"), b"\x0a\x02hi")

    def test_make_command_structure(self):
        blob = proto.make_command(2, "ra2yrproto.commands.GetGameState")
        self.assertEqual(proto.one(blob, 1), 2)
        type_name, payload = proto.any_unpack(proto.sub(blob, 3))
        self.assertEqual(type_name, "ra2yrproto.commands.GetGameState")
        self.assertEqual(payload, b"")

    def test_make_command_blocking_sets_field_four(self):
        blob = proto.make_command(2, "X", b"", blocking=True)
        self.assertEqual(proto.one(blob, 4), 1)
        blob = proto.make_command(2, "X", b"", blocking=False)
        self.assertIsNone(proto.one(blob, 4))


class TestDecoding(unittest.TestCase):
    def test_any_round_trip(self):
        blob = proto.any_pack("ra2yrproto.commands.UnitOrder", b"\x08\x01")
        type_name, payload = proto.any_unpack(blob)
        self.assertEqual(type_name, "ra2yrproto.commands.UnitOrder")
        self.assertEqual(payload, b"\x08\x01")

    def test_any_unpack_strips_prefix(self):
        blob = proto.pb_str(1, "type.googleapis.com/a.B") + proto.pb_bytes(2, b"z")
        self.assertEqual(proto.any_unpack(blob), ("a.B", b"z"))

    def test_fields_and_fmap(self):
        blob = proto.pb_uint(1, 7) + proto.pb_bytes(2, b"xy") + proto.pb_uint(1, 9)
        self.assertEqual(list(proto.fields(blob)),
                         [(1, 0, 7), (2, 2, b"xy"), (1, 0, 9)])
        grouped = proto.fmap(blob)
        self.assertEqual(grouped[1], [(0, 7), (0, 9)])
        self.assertEqual(grouped[2], [(2, b"xy")])

    def test_empty_message(self):
        self.assertEqual(list(proto.fields(b"")), [])
        self.assertEqual(proto.one(b"", 3, "default"), "default")

    def test_packed_varints(self):
        blob = proto.varint(1) + proto.varint(300) + proto.varint(2)
        self.assertEqual(proto.packed_varints(blob), [1, 300, 2])

    def test_repeated_ints_accepts_packed_and_plain(self):
        entries = [(0, 5), (2, proto.varint(6) + proto.varint(7)), (0, 8)]
        self.assertEqual(proto.repeated_ints(entries), [5, 6, 7, 8])

    def test_signed64(self):
        self.assertEqual(proto.signed64(0), 0)
        self.assertEqual(proto.signed64(2 ** 64 - 1), -1)
        self.assertEqual(proto.signed64(2 ** 64 - 2), -2)
        self.assertEqual(proto.signed64(2 ** 63), -(2 ** 63))

    def test_unsupported_wire_type_raises(self):
        # 线类型 3 未定义
        with self.assertRaises(ProtocolError):
            list(proto.fields(b"\x0b"))


if __name__ == "__main__":
    unittest.main()
