#!/usr/bin/env python3
"""汇总探针记录的 UDP 包流向。

`ra2yrcpp.json` 里设 `"trafficFilename": "traffic.pb"` 后，探针把**每一个收发的 UDP 包**
（含方向与原始字节）写进该文件，格式是 gzip 压缩的、长度前缀的 protobuf 流，每条为
`ra2yr.TunnelPacket`：

```protobuf
message TunnelPacket {
  uint32 source = 1;       // 发端节点号；0 是自己
  uint32 destination = 2;  // 收端节点号
  bytes  data = 3;
}
```

节点号是游戏内部的假 IPX 地址，spawner 的 NetHack 层再把它换成真实 ip:port。

这是判「网络到底有没有通」的硬证据：只有单向 = 对端没回、或包被丢；两边都没有 = 压根没进
网络代码（例如退回了单机 Skirmish）。注意**游戏被杀在半途时 gzip 流是截断的**，本工具按
能读到的部分汇总，不报错。

用法：

```sh
python3 tools/read_traffic.py /mnt/d/Games/ra2probe/traffic.pb
python3 tools/read_traffic.py --samples 5 /mnt/d/Games/ra2probe/traffic.pb
```
"""
import argparse
import collections
import pathlib
import sys
import zlib

#: gzip 容器的 window bits，交给 `zlib` 解压。
GZIP_WBITS = 16 + zlib.MAX_WBITS


def decompress_partial(raw: bytes) -> bytes:
    """解出 gzip 流的全部可读内容，容忍尾部截断。

    @param raw: `traffic.pb` 的原始字节。
    @returns: 解压后的 protobuf 流。
    @raises SystemExit: 连 gzip 头都读不出来时。
    """
    if not raw:
        return b""
    obj = zlib.decompressobj(GZIP_WBITS)
    try:
        out = obj.decompress(raw)
    except zlib.error as exc:
        print(f"解压失败（可能不是 gzip 流）：{exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    return out + obj.flush()


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    """读一个 protobuf 变长整数。

    @param buf: 数据。
    @param pos: 起始位置。
    @returns: (值, 新位置)。
    @raises IndexError: 数据在变长整数中途结束。
    """
    shift = value = 0
    while True:
        byte = buf[pos]
        pos += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, pos
        shift += 7


def read_fields(buf: bytes) -> dict[int, int | bytes]:
    """把一条消息读成「字段号 -> 值」。

    @param buf: 单条消息的字节。
    @returns: 字段号到取值的映射；变长整数给 `int`，长度前缀给 `bytes`。
    """
    out: dict[int, int | bytes] = {}
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = read_varint(buf, pos)
        elif wire == 2:
            size, pos = read_varint(buf, pos)
            value, pos = buf[pos:pos + size], pos + size
        else:
            break
        out.setdefault(field, value)
    return out


def read_packets(data: bytes) -> list[tuple[int, int, int]]:
    """把 protobuf 流读成包列表。

    @param data: 解压后的流。
    @returns: 每项为 (source, destination, 负载字节数)；流尾不完整时丢弃尾部。
    """
    packets: list[tuple[int, int, int]] = []
    pos = 0
    while pos < len(data):
        try:
            size, pos = read_varint(data, pos)
        except IndexError:
            break
        if pos + size > len(data):
            break                       # 尾部被截断
        fields = read_fields(data[pos:pos + size])
        pos += size
        packets.append((int(fields.get(1, 0) or 0),
                        int(fields.get(2, 0) or 0),
                        len(fields.get(3, b"") or b"")))
    return packets


def summarize(path: pathlib.Path, samples: int) -> int:
    """打印一个 `traffic.pb` 的流向汇总。

    @param path: 待读的文件。
    @param samples: 打印前几个包的明细条数。
    @returns: 进程退出码。
    """
    raw = path.read_bytes()
    print(f"{path}：{len(raw)} 字节")
    if not raw:
        print("  空文件——该实例一个包都没收发（没进网络代码，或包方向全被挡）。")
        return 0
    packets = read_packets(decompress_partial(raw))
    print(f"  {len(packets)} 个包")
    if not packets:
        return 0
    by_direction = collections.Counter((src, dst) for src, dst, _ in packets)
    for (src, dst), count in by_direction.most_common():
        print(f"  source={src} -> destination={dst}：{count} 个")
    senders = {src for src, _, _ in packets}
    receivers = {dst for _, dst, _ in packets}
    print(f"  发出方节点 {sorted(senders)}，接收方节点 {sorted(receivers)}")
    for (src, dst, size) in packets[:samples]:
        print(f"    source={src} destination={dst} {size} 字节")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    @param argv: 参数列表，默认取 `sys.argv`。
    @returns: 进程退出码。
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("traffic", type=pathlib.Path, nargs="+", help="traffic.pb 的路径")
    parser.add_argument("--samples", type=int, default=0, help="每个文件打印前几个包的明细")
    args = parser.parse_args(argv)

    for path in args.traffic:
        if not path.is_file():
            print(f"找不到 {path}", file=sys.stderr)
            return 2
        summarize(path, args.samples)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
