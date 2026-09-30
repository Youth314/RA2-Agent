"""UDP 包流向汇总工具的测试。

离线假件：自己拼 gzip + 长度前缀的 `TunnelPacket` 流，也造截断流。
"""
import gzip
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import read_traffic  # noqa: E402


def varint(value: int) -> bytes:
    """把一个整数编码成 protobuf 变长整数。

    @param value: 非负整数。
    @returns: 变长字节。
    """
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def packet(source: int, destination: int, payload: bytes) -> bytes:
    """造一条 `TunnelPacket`。

    @param source: 发端节点号。
    @param destination: 收端节点号。
    @param payload: 负载。
    @returns: 长度前缀的完整消息。
    """
    body = (b"\x08" + varint(source) + b"\x10" + varint(destination)
            + b"\x1a" + varint(len(payload)) + payload)
    return varint(len(body)) + body


def stream(packets: list[bytes]) -> bytes:
    """把若干条消息压成 gzip 流。

    @param packets: 已编码的消息。
    @returns: gzip 字节。
    """
    return gzip.compress(b"".join(packets))


class ReadTrafficTest(unittest.TestCase):
    """解码、汇总与截断容忍。"""

    def setUp(self) -> None:
        """建一个临时目录。"""
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self.path = pathlib.Path(self._dir.name) / "traffic.pb"

    def test_reads_both_directions(self) -> None:
        """双向的包都应读出来，方向保持原样。"""
        self.path.write_bytes(stream([packet(0, 1, b"a" * 71), packet(1, 0, b"b" * 20)]))
        got = read_traffic.read_packets(read_traffic.decompress_partial(self.path.read_bytes()))
        self.assertEqual(got, [(0, 1, 71), (1, 0, 20)])

    def test_empty_file_is_empty(self) -> None:
        """空文件解出零个包。"""
        self.path.write_bytes(b"")
        self.assertEqual(read_traffic.decompress_partial(b""), b"")
        self.assertEqual(read_traffic.read_packets(b""), [])

    def test_tolerates_truncated_tail(self) -> None:
        """被杀在半途的 gzip 流：尾部缺失不该抛错，已解出的包照读。"""
        full = stream([packet(0, 1, b"x" * 8) for _ in range(200)])
        self.path.write_bytes(full[:len(full) * 9 // 10])
        got = read_traffic.read_packets(read_traffic.decompress_partial(self.path.read_bytes()))
        self.assertTrue(got, "只切掉尾部时前面的包应已解出")
        self.assertTrue(all(entry == (0, 1, 8) for entry in got))

    def test_heavily_truncated_stream_does_not_raise(self) -> None:
        """砍到一半时 `zlib` 可能一个块都凑不齐，但也不该抛错。"""
        full = stream([packet(0, 1, b"x" * 8) for _ in range(200)])
        self.path.write_bytes(full[:len(full) // 2])
        got = read_traffic.read_packets(read_traffic.decompress_partial(self.path.read_bytes()))
        self.assertTrue(all(entry == (0, 1, 8) for entry in got))

    def test_tolerates_trailing_partial_message(self) -> None:
        """尾部不完整的那条消息应被丢掉，前面的照读。"""
        good = packet(0, 1, b"y" * 4)
        data = good + varint(1000) + b"\x08\x00"
        got = read_traffic.read_packets(data)
        self.assertEqual(got, [(0, 1, 4)])

    def test_summarize_reports_directions(self) -> None:
        """汇总应把两个方向分别计数。"""
        self.path.write_bytes(stream([packet(0, 1, b"a"), packet(0, 1, b"a"), packet(1, 0, b"b")]))
        self.assertEqual(read_traffic.summarize(self.path, samples=1), 0)

    def test_summarize_empty_file(self) -> None:
        """空文件应给出可读的解释而不是报错。"""
        self.path.write_bytes(b"")
        self.assertEqual(read_traffic.summarize(self.path, samples=0), 0)

    def test_missing_file_fails(self) -> None:
        """路径不存在时返回非零。"""
        missing = pathlib.Path(self._dir.name) / "nope.pb"
        self.assertEqual(read_traffic.main([str(missing)]), 2)


if __name__ == "__main__":
    unittest.main()
