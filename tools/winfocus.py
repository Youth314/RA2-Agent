#!/usr/bin/env python3
"""Windows 窗口置前工具，用于规避 RA2 的失焦暂停。

RA2 单机在窗口失焦时主循环不推进，命令只排队不执行。本模块经 PowerShell
调用 user32，把游戏窗口置前或移开。

用法:
    python3 winfocus.py list              # 列出可见窗口
    python3 winfocus.py fg                # 打印当前前台窗口
    python3 winfocus.py focus <标题子串>   # 把匹配窗口置前
    python3 winfocus.py game              # 把游戏窗口置前
    python3 winfocus.py away              # 把焦点移离游戏
"""
import base64
import subprocess
import sys

PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
GAME_TITLE = "Yuri's Revenge"

# 枚举与取标题全部放在 C# 内，避免 PowerShell 委托里 Write-Output 回不到管道，
# 以及 GetWindowTextW 按 ANSI 编组导致的乱码。
_PS_HEADER = r'''
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -TypeDefinition @"
using System;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();

  public static List<string> List() {
    var res = new List<string>();
    EnumWindows(delegate(IntPtr h, IntPtr l) {
      if (IsWindowVisible(h)) {
        var sb = new StringBuilder(512);
        GetWindowTextW(h, sb, 512);
        string t = sb.ToString();
        if (t.Length > 0) res.Add(h.ToInt64().ToString() + "\t" + t);
      }
      return true;
    }, IntPtr.Zero);
    return res;
  }
  public static string Foreground() {
    IntPtr h = GetForegroundWindow();
    var sb = new StringBuilder(512);
    GetWindowTextW(h, sb, 512);
    return h.ToInt64().ToString() + "\t" + sb.ToString();
  }
  public static bool Focus(long h) {
    ShowWindow(new IntPtr(h), 9);
    System.Threading.Thread.Sleep(250);
    return SetForegroundWindow(new IntPtr(h));
  }
}
"@
'''


def _run(script):
    enc = base64.b64encode((_PS_HEADER + script).encode("utf-16-le")).decode()
    p = subprocess.run([PS, "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", enc],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=40)
    if p.returncode != 0:
        raise RuntimeError(f"PowerShell 失败: {(p.stderr or '').strip()[:300]}")
    return (p.stdout or "").replace("\r", "").strip()


def _parse(line):
    if "\t" in line:
        handle, title = line.split("\t", 1)
        try:
            return int(handle), title
        except ValueError:
            return None
    return None


def list_windows():
    """返回当前可见的顶层窗口 [(handle, title)]。"""
    out = _run('[W]::List() | ForEach-Object { $_ }')
    return [w for w in (_parse(ln) for ln in out.splitlines()) if w]


def foreground():
    """返回当前前台窗口的 (handle, title)。"""
    return _parse(_run('[W]::Foreground()')) or (0, "")


def find_window(substring):
    """按标题子串查找窗口，返回 handle；未找到返回 None。"""
    for handle, title in list_windows():
        if substring.lower() in title.lower():
            return handle
    return None


def focus_handle(handle):
    """还原并置前指定窗口。"""
    return _run(f'[W]::Focus({handle})').strip().lower() == "true"


def focus_title(substring):
    handle = find_window(substring)
    return focus_handle(handle) if handle is not None else False


def focus_game():
    return focus_title(GAME_TITLE)


SKIP_TITLES = ("program manager", "default ime", "msctfime ui", "yuri's revenge")


def focus_away():
    """把焦点移离游戏，用于验证失焦行为。返回 (handle, title)。"""
    for handle, title in list_windows():
        if any(s in title.lower() for s in SKIP_TITLES):
            continue
        if focus_handle(handle):
            return handle, title
    return None, None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd == "list":
        for handle, title in list_windows():
            print(f"{handle:>8}  {title}")
    elif cmd == "fg":
        handle, title = foreground()
        print(f"{handle}  {title}")
    elif cmd == "focus":
        print("ok" if focus_title(sys.argv[2]) else "not found")
    elif cmd == "game":
        print("ok" if focus_game() else "not found")
    elif cmd == "away":
        print(focus_away())
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
