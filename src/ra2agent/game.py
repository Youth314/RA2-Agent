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
#: 起游戏后端口多久还没在听就值得怀疑。实测约 3 秒起来，留足余量。
STARTUP_GRACE = 60.0
#: 判「主循环暂停」要帧号停住多少秒。**按帧号判，不按前台窗口标题**：同桌面两个
#: 同名实例时前台判据必然对至少一方为假。
LOOP_STALL_SECONDS = 2.0


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
    #: 本进程发起过启动后已过多少秒；没发起过则为 `None`。
    waited: float | None = None

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
                 window_probe=None, port_probe=None, now=time.time,
                 path_probe=None, pid_window_probe=None, handle_focus=None):
        self.runner = runner or default_runner
        self.host = host
        self.port = port
        self.game_dir = game_dir
        self.game_dir_wsl = game_dir_wsl
        self.exe = exe
        self.crash_report = CRASH_REPORT if crash_report is None else crash_report
        self.focus_probe = focus_probe or winfocus.is_game_foreground
        self.focus_reset = focus_reset or winfocus.reset
        #: 标题含游戏名的窗口清单。报「置前失败」时要能说清找到了几个。
        self.window_probe = window_probe or winfocus.game_windows
        #: 进程路径与窗口句柄：用来在同名实例之间认准自己那一份。
        self.process_path = path_probe or winfocus.process_path
        self.window_of_process = pid_window_probe or winfocus.window_of_process
        self.focus_handle = handle_focus or winfocus.focus_handle
        #: 上一次 `focus_game()` 走的哪条路，供 `game focus` 回报。
        self.last_focus_route = ""
        self.port_probe = port_probe or self._probe_over_socket
        self.now = now
        #: 本进程最近一次 `launch()` 的时刻；用于判断留证是不是这次的事。
        self.launched_at = None

    # ------------------------------------------------------------ 观测
    def processes(self):
        """本游戏的可执行文件当前有几个进程。"""
        result = self._run([TASKLIST, "/FI", f"IMAGENAME eq {self.exe}",
                            "/FO", "CSV", "/NH"])
        return parse_processes(result.stdout)

    def port_open(self):
        """服务端口是否在听。"""
        return self.port_probe()

    def _probe_over_socket(self):
        """真去连一次服务端口。

        这是默认实现；**测试必须换掉它**——否则游戏真在跑时，用例会因为本机
        14521 有人在听而得出截然不同的结论。
        """
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

    def crash_evidence(self):
        """与本次启动有关的崩溃报告距今多少秒；无关或没有则为 `None`。

        刚 `game start` 完那几秒，进程在、端口还没通。此时若报一份两小时前的
        报告，模型会把「正在启动」读成「崩过」，故报告必须比本次启动新才算数。
        """
        age = self.crash_report_age()
        if age is None or self.launched_at is None:
            return age
        if self.now() - age < self.launched_at:
            return None
        return age

    # ------------------------------------------------------------ 动作
    def launch(self):
        """经 PowerShell 起游戏。

        必须给绝对路径：`cmd /c start` 从 WSL 启动会静默失败。
        """
        self.launched_at = self.now()
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

        先按**进程路径**认准自己那一份（同桌面两个同名实例时按标题找有歧义：先找到
        的那个未必是我们连的那一份），认不出再退回标题路径。标题那条路走
        `winfocus.reset`：`SetForegroundWindow` 对已经在前台的窗口不产生切换，
        先移开再置前才造得出真正的切换。
        """
        pid = self._own_pid()
        if pid is not None:
            handle = self.window_of_process(pid)
            if handle is not None and self.focus_handle(handle):
                self.last_focus_route = f"按进程 {pid} 认准"
                return True
        self.last_focus_route = "按标题取第一个（同名实例分辨不出是哪一份）"
        return self.focus_reset()

    def _own_pid(self):
        """可执行文件落在 `self.game_dir` 里的那个游戏进程；认不出给 `None`。

        比目录而不是比前缀：`ra2probe` 与 `ra2probe-b` 互为前缀，比前缀会认错人。
        """
        wanted = (self.game_dir or "").rstrip("\\/").lower()
        if not wanted:
            return None
        for process in self.processes():
            path = (self.process_path(process.pid) or "").strip().lower()
            if path and path.rsplit("\\", 1)[0] == wanted:
                return process.pid
        return None

    # ------------------------------------------------------------ 报告
    def inspect(self):
        """巡检一次：进程、端口、留证、焦点。"""
        processes = self.processes()
        return HostState(
            processes=processes,
            listening=self.port_open(),
            crash_age=self.crash_evidence(),
            focused=self.focus_probe() if processes else None,
            waited=None if self.launched_at is None else max(0.0, self.now() - self.launched_at),
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
                waited = "" if state.waited is None else f"，已等 {int(state.waited)} 秒"
                lines.append(f"游戏：正在启动（PID {pids}{waited}），端口 {self.port} 还没通"
                             f"——服务约 3 秒后开始听，进对局还要更久。用 game status 再看。")
                if state.waited is not None and state.waited > STARTUP_GRACE:
                    lines.append(f"注意：已等 {int(state.waited)} 秒还没在听，"
                                 f"可能卡住或起崩了。")
            else:
                focus = ("窗口在前台" if state.focused
                         else "窗口不在前台（主循环未必停——看帧号是否推进）")
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
