#!/usr/bin/env python3
"""向用户发 Windows 通知，用于长批次测试的完成与确认提示。

用于「Agent 占用焦点跑测试」的场景：批次开始时焦点被游戏占走，用户无法
看到终端输出，因此批次结束时用系统通知提醒。

用法:
    python3 notify.py "标题" "内容"       # 发通知
    python3 notify.py --test              # 依次测试各通道
"""
import base64
import subprocess
import sys

PS = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"

# 用已注册的 PowerShell AppID，避免自定义 AppID 未注册导致 toast 不显示。
APP_ID = ("{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}"
          "\\WindowsPowerShell\\v1.0\\powershell.exe")


def _xml_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&apos;"))


def _run(script, timeout=30):
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    p = subprocess.run([PS, "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", enc],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def toast(title, body, app_id=APP_ID):
    """弹出一条 Windows 通知。返回 (是否成功, 诊断信息)。"""
    xml = (
        '<toast duration="long">'
        '<visual><binding template="ToastGeneric">'
        f"<text>{_xml_escape(title)}</text>"
        f"<text>{_xml_escape(body)}</text>"
        "</binding></visual>"
        '<audio src="ms-winsoundevent:Notification.Default"/>'
        "</toast>"
    )
    script = f'''
$ErrorActionPreference = 'Stop'
try {{
  [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime]
  [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime]
  $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
  $doc.LoadXml(@"
{xml}
"@)
  $t = New-Object Windows.UI.Notifications.ToastNotification $doc
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{app_id}").Show($t)
  Write-Output "OK"
}} catch {{
  Write-Output "FAIL: $($_.Exception.Message)"
}}
'''
    code, out, err = _run(script)
    if code != 0:
        return False, (err or out)[:200]
    return out == "OK", out[:200]


def messagebox(title, body, timeout=60):
    """弹出一个置顶消息框。以独立进程启动，不阻塞调用方。"""
    script = f'''
Add-Type -AssemblyName System.Windows.Forms
$null = [System.Windows.Forms.MessageBox]::Show(
  "{_xml_escape(body)}", "{_xml_escape(title)}",
  [System.Windows.Forms.MessageBoxButtons]::OK,
  [System.Windows.Forms.MessageBoxIcon]::Information,
  [System.Windows.Forms.MessageBoxDefaultButton]::Button1,
  [System.Windows.Forms.MessageBoxOptions]::ServiceNotification)
Write-Output "OK"
'''
    enc = base64.b64encode(script.encode("utf-16-le")).decode()
    p = subprocess.Popen([PS, "-NoProfile", "-NonInteractive",
                          "-EncodedCommand", enc],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return p


def beep():
    """播放系统提示音，作为通知的听觉补充。"""
    _run('[System.Media.SystemSounds]::Exclamation.Play(); Write-Output "OK"')


def notify(title, body):
    """发通知：toast + 提示音；toast 失败时退回消息框。"""
    ok, info = toast(title, body)
    beep()
    if not ok:
        messagebox(title, body)
    return ok, info


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        ok, info = toast("RA2 Agent 测试", "这是一条 toast 通知")
        print(f"toast: ok={ok} info={info}")
        beep()
        print("beep: 已播放")
        if len(sys.argv) > 2 and sys.argv[2] == "--box":
            messagebox("RA2 Agent 测试", "这是一条消息框通知")
            print("messagebox: 已启动")
        return 0
    if len(sys.argv) >= 3:
        ok, info = notify(sys.argv[1], sys.argv[2])
        print(f"notify: ok={ok} info={info}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
