#!/usr/bin/env python3
"""去掉 `gamemd` 的单实例守卫，使同一台机器能同时跑两个实例。

守卫在 `gamemd` 自己的 `Startup.CPP` 里（`gamemd.exe` 与 CnCNet 的 spawn 版同址同字节）：
以固定名建互斥体，`GetLastError() == ERROR_ALREADY_EXISTS` 时把已有窗口置前、关掉句柄、
从 `WinMain` 返回 0——**干净退出**，既没有崩溃报告也没有日志（那句提示要经
`0x4068E0`，而它已被 patch 成 `ret`）。所以第二个实例表现为「起来了、约 130 ms 后无声消失」。

```text
006bbe56  push  0x840f14                 ; "29e3bb2a-2f36-11d3-a72c-0090272fa661"
006bbe5f  call  dword ptr [0x7e1248]     ; CreateMutexA
006bbe6a  call  dword ptr [0x7e1200]     ; GetLastError
006bbe70  cmp   eax, 0xb7                ; ERROR_ALREADY_EXISTS = 183
006bbe75  jne   0x6bbed6                 ; 不等 -> 正常启动
006bbe77  ...                            ; 已存在 -> 置前 + 退出
```

`.text` 一一映射（VA 0x401000 == 文件偏移 0x1000），故文件偏移 = VA - 0x400000。
本工具把比较的立即数改成 `0xFFFFFFFF`：`GetLastError` 永不等于此值，分支恒不成立，
其余启动流程一字未动。

用法：

```sh
python3 tools/patch_single_instance.py --check    /mnt/d/Games/ra2probe/gamemd-spawn-ra2yrcpp.exe
python3 tools/patch_single_instance.py --patch    /mnt/d/Games/ra2probe/gamemd-spawn-ra2yrcpp.exe
python3 tools/patch_single_instance.py --restore  /mnt/d/Games/ra2probe/gamemd-spawn-ra2yrcpp.exe
```

改动前须确认没有实例在跑：运行中的映像不可写。第二游戏目录的该 exe 常与第一个目录
**共享硬链接**，故补一次两处都生效，还原同理。
"""
import argparse
import pathlib
import shutil
import sys

#: `cmp eax, 0xB7` 的指令起点（VA 0x6BBE70）。
GUARD_OFFSET = 0x2BBE70
#: 守卫处的原始字节：`cmp eax,0xB7` + `jne +0x5F`。
GUARD_BYTES = bytes.fromhex("3db7000000755f")
#: 比较的立即数（VA 0x6BBE71），补丁改写这里。
IMM_OFFSET = GUARD_OFFSET + 1
IMM_PATCHED = bytes.fromhex("ffffffff")
#: 打过补丁后守卫处的完整字节。
GUARD_PATCHED = GUARD_BYTES[:1] + IMM_PATCHED + GUARD_BYTES[1 + len(IMM_PATCHED):]

BACKUP_SUFFIX = ".si-bak"


def read_state(path: pathlib.Path) -> str:
    """返回 `"original"`、`"patched"` 或 `"unknown"`。

    @param path: 待检查的 exe。
    @returns: 守卫处的字节所对应的状态。
    """
    data = path.read_bytes()
    guard = data[GUARD_OFFSET:GUARD_OFFSET + len(GUARD_BYTES)]
    if guard == GUARD_BYTES:
        return "original"
    if guard == GUARD_PATCHED:
        return "patched"
    return "unknown"


def is_guarded(path: pathlib.Path) -> bool:
    """守卫处是否是本工具认得的字节。

    @param path: 待检查的 exe。
    @returns: 认得为真；换了一个 build 或已被别的工具改过为假。
    """
    return read_state(path) != "unknown"


def report_unknown(path: pathlib.Path) -> None:
    """把无法识别的守卫字节打到标准错误。

    @param path: 待检查的 exe。
    """
    data = path.read_bytes()
    guard = data[GUARD_OFFSET:GUARD_OFFSET + len(GUARD_BYTES)]
    print(f"{path} 在 0x{GUARD_OFFSET:X} 处是 {guard.hex(' ')}，"
          f"既不是原始守卫也不是本工具写的补丁；换一个 build 或先人工确认。",
          file=sys.stderr)


def cmd_check(path: pathlib.Path) -> int:
    """只报状态，不改文件，也不据状态返回非零。

    @param path: 待检查的 exe。
    @returns: 0，除非守卫处无法识别。
    """
    state = read_state(path)
    print(f"{path}: {state}")
    links = path.stat().st_nlink
    if links > 1:
        print(f"  该文件有 {links} 个硬链接，改动会同时作用于所有链接。")
    return 0 if state != "unknown" else 1


def cmd_patch(path: pathlib.Path) -> int:
    """把守卫的比较立即数改成永不相等。

    @param path: 待改写的 exe。
    @returns: 进程退出码。
    """
    if not is_guarded(path):
        report_unknown(path)
        return 2
    if read_state(path) == "patched":
        print(f"{path}: 已经是打过补丁的状态，无需重复。")
        return 0
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copyfile(path, backup)
        print(f"已备份到 {backup}")
    data = bytearray(path.read_bytes())
    data[IMM_OFFSET:IMM_OFFSET + len(IMM_PATCHED)] = IMM_PATCHED
    path.write_bytes(bytes(data))
    print(f"已打补丁：0x{IMM_OFFSET:X} <- {IMM_PATCHED.hex(' ')}")
    return 0


def cmd_restore(path: pathlib.Path) -> int:
    """从备份还原。

    @param path: 待还原的 exe。
    @returns: 进程退出码。
    """
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if not backup.exists():
        print(f"没有备份 {backup}，无法还原。", file=sys.stderr)
        return 1
    shutil.copyfile(backup, path)
    print(f"已从 {backup} 还原")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    @param argv: 参数列表，默认取 `sys.argv`。
    @returns: 进程退出码。
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("exe", type=pathlib.Path, help="gamemd-spawn-ra2yrcpp.exe 的路径")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="只报状态（默认）")
    action.add_argument("--patch", action="store_true", help="打补丁")
    action.add_argument("--restore", action="store_true", help="从 .si-bak 还原")
    args = parser.parse_args(argv)

    if not args.exe.is_file():
        print(f"找不到 {args.exe}", file=sys.stderr)
        return 2
    if args.patch:
        return cmd_patch(args.exe)
    if args.restore:
        return cmd_restore(args.exe)
    return cmd_check(args.exe)


if __name__ == "__main__":
    raise SystemExit(main())
