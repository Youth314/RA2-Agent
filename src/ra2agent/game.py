"""游戏进程本身：起停、端口、崩溃留证、窗口焦点。

与 `Client` 的分工：`Client` 管对局内的连接，端口通了才有意义；本模块管游戏
进程，故游戏没在跑时它仍要能用——「启动游戏」这个动作不能依赖游戏已经启动。

外部命令一律经 `runner`（默认 `subprocess.run`），故本模块离线可测。
"""
import os
import socket
import subprocess
import time
from dataclasses import dataclass

from .constants import DEFAULT_HOST, DEFAULT_PORT
from .errors import Ra2Error
from . import winfocus

#: 探针游戏环境的 Windows 路径与 WSL 路径，见 `.agents/notes/开发环境.md`。
GAME_DIR = r"D:\Games\ra2probe"
GAME_DIR_WSL = "/mnt/d/Games/ra2probe"
#: 入口可执行文件。ra2yrcpp 由它拉起，故「游戏在跑」看的是它。
GAME_EXE = "gamemd-spawn-ra2yrcpp.exe"
GAME_ARG = "-SPAWN"
#: 崩溃报告，每次崩溃覆盖上一份；`tools/watchdog.sh` 之外的第二处留证。
CRASH_REPORT = GAME_DIR_WSL + "/EXCEPT_CNCNET.TXT"

POWERSHELL = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
TASKLIST = "/mnt/c/Windows/System32/tasklist.exe"
TASKKILL = "/mnt/c/Windows/System32/taskkill.exe"

#: 外部命令的上限。tasklist 要一两秒，PowerShell 起进程更久。
COMMAND_TIMEOUT = 30.0
#: 端口探测的上限。服务端在听就是立刻通。
PROBE_TIMEOUT = 1.0


@dataclass(frozen=True)
class ProcessInfo:
    """一条 `tasklist` 记录。"""

    image: str
    pid: int


@dataclass(frozen=True)
class HostState:
    """一次宿主侧巡检的结果。"""

    processes: tuple
    listening: bool
    crash_age: float | None
    #: 没有进程时为 `None`：没有窗口就无所谓焦点。
    focused: bool | None

    @property
    def running(self):
        """游戏进程是否在。"""
        return bool(self.processes)


def default_runner(argv, timeout=COMMAND_TIMEOUT):
    """默认的外部命令执行器。

    `tasklist` 的提示行按 Windows 本地编码输出，故解码必须容错，否则会抛
    `UnicodeDecodeError` 而不是给出可用结果。
    """
    return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def parse_processes(text):
    """从 `tasklist /FO CSV /NH` 的输出里取进程。

    没匹配时 tasklist 打一行本地化提示（解出来是乱码），故只认以引号开头的 CSV
    行，其余一律忽略。
    """
    found = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        parts = [part.strip('"') for part in line.split('","')]
        if len(parts) < 2 or not parts[1].isdigit():
            continue
        found.append(ProcessInfo(image=parts[0], pid=int(parts[1])))
    return tuple(found)


def describe_age(seconds):
    """把秒数说成「多久以前」。"""
    if seconds < 60:
        return f"{int(seconds)} 秒前"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    return f"{int(seconds // 86400)} 天前"


class GameHost:
    """游戏进程的宿主侧操作。"""

    def __init__(self, runner=None, host=DEFAULT_HOST, port=DEFAULT_PORT,
                 game_dir=GAME_DIR, game_dir_wsl=GAME_DIR_WSL, exe=GAME_EXE,
                 crash_report=None, focus_probe=None, focus_reset=None,
                 now=time.time):
        self.runner = runner or default_runner
        self.host = host
        self.port = port
        self.game_dir = game_dir
        self.game_dir_wsl = game_dir_wsl
        self.exe = exe
        self.crash_report = CRASH_REPORT if crash_report is None else crash_report
        self.focus_probe = focus_probe or winfocus.is_game_foreground
        self.focus_reset = focus_reset or winfocus.reset
        self.now = now

    # ------------------------------------------------------------ 观测
    def processes(self):
        """本游戏的可执行文件当前有几个进程。"""
        result = self._run([TASKLIST, "/FI", f"IMAGENAME eq {self.exe}",
                            "/FO", "CSV", "/NH"])
        return parse_processes(result.stdout)

    def port_open(self):
        """服务端口是否在听。"""
        try:
            with socket.create_connection((self.host, self.port), timeout=PROBE_TIMEOUT):
                return True
        except OSError:
            return False

    def crash_report_age(self):
        """崩溃报告距今多少秒；没有报告返回 `None`。

        报告每次崩溃覆盖，故它的时间戳就是「上一次崩在什么时候」。
        """
        try:
            return max(0.0, self.now() - os.path.getmtime(self.crash_report))
        except OSError:
            return None

    # ------------------------------------------------------------ 动作
    def launch(self):
        """经 PowerShell 起游戏。

        必须给绝对路径：`cmd /c start` 从 WSL 启动会静默失败。
        """
        script = (f"Start-Process -FilePath '{self.game_dir}\\{self.exe}' "
                  f"-ArgumentList '{GAME_ARG}' -WorkingDirectory '{self.game_dir}'")
        self._run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script])

    def terminate(self):
        """杀掉游戏进程，返回被杀的 PID。"""
        pids = tuple(process.pid for process in self.processes())
        if pids:
            self._run([TASKKILL, "/IM", self.exe, "/F"])
        return pids

    def focus_game(self):
        """把游戏窗口置前，返回是否成功。

        失焦即暂停主循环，而**光把它设成前台不会恢复**：`SetForegroundWindow`
        对已经在前台的窗口不产生切换。实现见 `winfocus.reset`。
        """
        return self.focus_reset()

    # ------------------------------------------------------------ 报告
    def inspect(self):
        """巡检一次：进程、端口、留证、焦点。"""
        processes = self.processes()
        return HostState(
            processes=processes,
            listening=self.port_open(),
            crash_age=self.crash_report_age(),
            focused=self.focus_probe() if processes else None,
        )

    def describe(self, state):
        """把巡检结果说成人话，若干行，给 `game status` 用。"""
        lines = []
        if not state.processes:
            lines.append(f"游戏：未运行（无进程，端口 {self.port} "
                         f"{'在听' if state.listening else '不通'}）")
            lines.append("可用：game start 启动")
        else:
            pids = "、".join(str(process.pid) for process in state.processes)
            if not state.listening:
                lines.append(f"游戏：进程在（PID {pids}），端口 {self.port} 还没通——"
                             f"服务要几秒，用 game status 再看")
            else:
                focus = ("窗口在前台" if state.focused
                         else "窗口失焦，主循环暂停——用 game focus 抢回焦点")
                lines.append(f"游戏：运行中（PID {pids}），服务在听，{focus}")
        if state.crash_age is not None:
            lines.append(f"留证：崩溃报告 {describe_age(state.crash_age)}（{self.crash_report}）")
        return tuple(lines)

    # ------------------------------------------------------------ 内部
    def _run(self, argv, timeout=COMMAND_TIMEOUT):
        """跑一条外部命令，把「跑不起来」也变成人话。"""
        try:
            return self.runner(argv, timeout=timeout)
        except FileNotFoundError as error:
            raise Ra2Error(f"找不到 {argv[0]}——Windows 互操作不可用？") from error
        except subprocess.TimeoutExpired as error:
            raise Ra2Error(f"{os.path.basename(argv[0])} 超时（{timeout:.0f} 秒）") from error
