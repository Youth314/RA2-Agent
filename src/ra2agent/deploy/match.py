"""一局对局：名册、整局起停、逐参与者的就绪判定。

`game.py` 管的是「这台机器上的那个游戏」，一局对局却是**多个进程**。本模块把进程
管理升到对局级，并让每个参与者各有自己的目录、探针端口与身份。

为什么必须一起起：`-SPAWN` **不进大厅、不等对手**，游戏自己在加载界面等连接
（超时 `ConnTimeout`，默认 3600 帧约 60 秒）。只起一个实例的后果是它在加载界面
干等，然后判对方掉线——这不是 bug，是名册没起全。

外部命令与探针读取一律经注入的 `runner` 与 `probe`，故本模块离线可测。
"""
import json
import pathlib
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, fields, replace

from .game import (COMMAND_TIMEOUT, GAME_ARG, GAME_EXE, POWERSHELL, TASKKILL,
                   GameHost, default_runner)

#: 探针的就绪阶段。`STAGE_INGAME` 之前都还在加载。
STAGE_INGAME = 2

#: spawner 读的那份配置，每个参与者的游戏目录里各一份。
SPAWN_INI = "spawn.ini"
#: 渲染覆盖前的备份后缀。渲染错了还能退回去。
RENDER_BACKUP_SUFFIX = ".render-bak"


def windows_bool(value: bool) -> str:
    """把布尔写成游戏认的 `True`/`False`。

    @param value: 布尔值。
    @returns: `True` 或 `False`。
    """
    return "True" if value else "False"


def apply_rule_overrides(rules: MatchRules, overrides: list[str]) -> MatchRules:
    """按 `键=值` 覆盖规则，值的类型照该字段本来的类型转。

    给命令行与工具一个统一的口子，好让「换资金、关迷雾、换地图」不必改配置文件。

    @param rules: 底子。
    @param overrides: 形如 `["credits=20000", "fog_of_war=Yes"]`。
    @returns: 覆盖后的规则。
    @raises ValueError: 缺 `=`、键认不出、或值转不过去。
    """
    updated = rules
    for item in overrides:
        key, separator, raw = item.partition("=")
        key, raw = key.strip(), raw.strip()
        if not separator or not key:
            raise ValueError(f"规则覆盖要写成 键=值，收到的是 {item!r}")
        known = {field.name for field in fields(MatchRules)}
        if key not in known:
            raise ValueError(f"没有这条规则：{key!r}；有的是 {sorted(known)}")
        current = getattr(updated, key)
        try:
            if isinstance(current, bool):
                value: object = raw.lower() in {"1", "true", "yes", "on"}
            elif isinstance(current, int):
                value = int(raw)
            else:
                value = raw
        except ValueError as error:
            raise ValueError(f"规则 {key} 的值转不过去：{raw!r}") from error
        updated = replace(updated, **{key: value})
    return updated


def render_spawn_ini(participant: Participant, peers: tuple[Participant, ...],
                     rules: MatchRules) -> str:
    """渲染一方的 `spawn.ini`。

    这里的键原先散在两份文件里靠手改，两边容易漂。集中到名册之后，**镜像字段全部
    可推导**：自己的 `Port`/`Name`/`Side`/`Color` 取自己那份，`[OtherN]` 的四项取
    对端那份，其余来自 `rules`。

    键的顺序照当前可用的那份 `spawn.ini`，好在换渲染器时逐字对比。

    @param participant: 要渲染的一方。
    @param peers: 其余参与者；按顺序写成 `[Other1]`、`[Other2]`……
    @param rules: 本局规则。
    @returns: `spawn.ini` 的完整内容。
    """
    lines = [
        "[Settings]",
        f"AIDifficulty={rules.ai_difficulty}",
        f"ReconnectTimeout={rules.reconnect_timeout}",
        f"ConnTimeout={rules.conn_timeout}",
        f"Protocol={rules.protocol}",
        f"GameID={rules.game_id}",
        f"Port={participant.match_port}",
        f"Name={participant.name}",
        f"Scenario={rules.scenario}",
        f"Side={participant.side}",
        f"IsSpectator={windows_bool(participant.is_spectator)}",
        f"Color={participant.color}",
        f"AIPlayers={rules.ai_players}",
        f"Seed={rules.seed}",
        f"ShortGame={windows_bool(rules.short_game)}",
        f"NoGarrisons={windows_bool(rules.no_garrisons)}",
        f"MCVRedeploy={windows_bool(rules.mcv_redeploy)}",
        f"BuildOffAlly={windows_bool(rules.build_off_ally)}",
        f"Crates={windows_bool(rules.crates)}",
        f"NavalCombat={windows_bool(rules.naval_combat)}",
        f"AlliesAllowed={windows_bool(rules.allies_allowed)}",
        f"UnitCount={rules.unit_count}",
        f"GameSpeed={rules.game_speed}",
        f"Credits={rules.credits}",
        f"TechLevel={rules.tech_level}",
        f"FogOfWar={rules.fog_of_war}",
        f"MultiEngineer={rules.multi_engineer}",
        "",
        "[HouseHandicaps]",
        f"Multi2={rules.ai_handicap}",
        "",
        "[HouseCountries]",
        f"Multi2={rules.ai_country}",
        "",
        "[HouseColors]",
        f"Multi2={rules.ai_color}",
    ]
    for index, peer in enumerate(peers, start=1):
        lines += [
            "",
            f"[Other{index}]",
            f"Name={peer.name}",
            f"Side={peer.side}",
            f"Color={peer.color}",
            f"Ip={rules.peer_ip}",
            f"Port={peer.match_port}",
        ]
    return "\n".join(lines) + "\n"


def wsl_path(windows_path: str) -> str:
    """把 Windows 路径换成 WSL 挂载路径。

    只做盘符映射（`D:\\x` → `/mnt/d/x`），不做符号链接解析——`D:\\Games\\ra2probe`
    在 WSL 侧就是 `/mnt/d/Games/ra2probe`。

    @param windows_path: 形如 `D:\\Games\\ra2probe` 的绝对路径。
    @returns: 形如 `/mnt/d/Games/ra2probe` 的路径。
    @raises ValueError: 不是「盘符 + 反斜杠」开头的绝对路径。
    """
    match = re.fullmatch(r"([A-Za-z]):[\\/](.*)", windows_path)
    if match is None:
        raise ValueError(f"不是 Windows 绝对路径：{windows_path!r}")
    drive, rest = match.groups()
    return f"/mnt/{drive.lower()}/" + rest.replace("\\", "/")


@dataclass(frozen=True)
class Participant:
    """对局里的一方。"""

    #: 名册里的名字，同时是它在 `spawn.ini` 的 `[Settings] Name`。
    name: str
    #: 游戏目录的 Windows 路径；每个参与者一份，`ra2yrcpp.json` 与 `spawn.ini` 都在里面。
    game_dir: str
    #: 探针端口。同一台机器上必须各不相同。
    probe_port: int
    #: 对局的 UDP 端口（`spawn.ini` 的 `[Settings] Port`）。无隧道时就是自己的绑定
    #: 端口，对端的 `[Other1] Port` 指的也是它，所以必须各不相同。
    match_port: int
    #: `spawn.ini` 的 `[Settings] Side`。
    side: int
    #: `spawn.ini` 的 `[Settings] Color`。
    color: int
    #: 是否占一个观战位。观战方不下场，但仍占一份进程。
    is_spectator: bool = False

    @property
    def wsl_dir(self) -> str:
        """本参与者的游戏目录在 WSL 侧的路径。"""
        return wsl_path(self.game_dir)


@dataclass(frozen=True)
class MatchRules:
    """一局对局的规则。与参与者分开：那边是部署事实，这边是每局的选择。

    这些键原先散在两份 `spawn.ini` 里靠手改，两边容易漂；集中到这里之后由
    `render_spawn_ini()` 生成，两边必然一致。
    """

    #: 地图文件名。**换地图不只是改这个值**——游戏读的是 `Scenario` 指向的那份文件，
    #: 内容得先备好（`.mmx` 是二进制容器，`spawnmap.ini` 是从它解出来的纯文本）。
    scenario: str = "spawnmap.ini"
    #: 对端的地址。同机对战是回环。
    peer_ip: str = "127.0.0.1"
    #: 对局标识，两边必须一致。
    game_id: int = 3735928559
    #: 随机种子，两边必须一致。
    seed: int = 1
    protocol: int = 2
    #: 等对手连上的上限（帧）。60 fps 下 3600 帧约 60 秒。
    conn_timeout: int = 3600
    reconnect_timeout: int = 2400
    credits: int = 10000
    tech_level: int = 10
    #: `Yes`/`No` 写法，不是布尔——游戏两种都收，这里照原样写。
    fog_of_war: str = "No"
    unit_count: int = 10
    game_speed: int = 1
    crates: bool = False
    short_game: bool = True
    mcv_redeploy: bool = True
    build_off_ally: bool = True
    naval_combat: bool = True
    allies_allowed: bool = True
    no_garrisons: bool = False
    multi_engineer: str = "Yes"
    #: AI 席位数量与难度；两个真人时是 0。
    ai_players: int = 0
    ai_difficulty: int = 1
    #: AI 席位的 `[HouseHandicaps]`/`[HouseCountries]`/`[HouseColors]`，键都是 `Multi2`。
    ai_handicap: int = 2
    ai_country: int = 1
    ai_color: int = 1

    @classmethod
    def load(cls, data: dict) -> "MatchRules":
        """从名册的 `rules` 段读规则；没写的键用默认值。

        @param data: `rules` 段的对象。
        @returns: 规则。
        @raises ValueError: 认不出的键。
        """
        known = {field.name for field in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"名册的 rules 里有认不出的键：{sorted(unknown)}")
        return cls(**data)


@dataclass(frozen=True)
class MatchRoster:
    """一局对局的参加者与启动参数。从 `config/match.json` 读。"""

    #: 全部参与者进入对局的等待上限（秒）。
    ready_timeout: float = 120.0
    #: 相邻两次启动之间隔多久（秒）。`-SPAWN` 不等对手，起得过于集中会互相踩。
    launch_gap: float = 12.0
    #: 每局可以选的东西（地图、资金、迷雾……）。没写就用 `MatchRules` 的默认值。
    rules: MatchRules = MatchRules()
    players: tuple[Participant, ...] = ()

    @classmethod
    def load(cls, path) -> "MatchRoster":
        """从 JSON 读取名册。认不出的键报错，不静默忽略。

        @param path: `config/match.json` 的路径。
        @returns: 校验过的名册。
        @raises ValueError: 键认不出、参与者少于两个、名字或端口重复。
        """
        source = pathlib.Path(path)
        if not source.exists():
            raise FileNotFoundError(f"没有名册文件 {source}")
        data = json.loads(source.read_text(encoding="utf-8"))

        known = {field.name for field in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"{source.name} 里有认不出的键：{sorted(unknown)}")

        player_keys = {field.name for field in fields(Participant)}
        players = []
        for raw in data.get("players", []):
            extra = set(raw) - player_keys
            if extra:
                raise ValueError(f"{source.name} 的参与者里有认不出的键：{sorted(extra)}")
            players.append(Participant(**raw))

        roster = cls(ready_timeout=data.get("ready_timeout", cls.ready_timeout),
                     launch_gap=data.get("launch_gap", cls.launch_gap),
                     rules=MatchRules.load(data.get("rules", {})),
                     players=tuple(players))
        roster.validate()
        return roster

    def validate(self) -> None:
        """核对名册本身自洽。

        @raises ValueError: 参与者少于两个、名字/目录/探针端口/对局端口重复。
        """
        if len(self.players) < 2:
            raise ValueError(f"一局至少两个参与者，名册里只有 {len(self.players)} 个")
        for field_name, values in (("名字", [p.name for p in self.players]),
                                   ("目录", [p.game_dir for p in self.players]),
                                   ("探针端口", [p.probe_port for p in self.players]),
                                   ("对局端口", [p.match_port for p in self.players])):
            if len(set(values)) != len(values):
                raise ValueError(f"参与者的{field_name}必须各不相同：{values}")

    def peers_of(self, name: str) -> tuple[Participant, ...]:
        """除某人之外的其余参与者。

        @param name: 名册里的名字。
        @returns: 其余参与者，顺序与名册一致。
        """
        return tuple(player for player in self.players if player.name != name)

    def get(self, name: str) -> Participant:
        """按名字取参与者。

        @param name: 名册里的名字。
        @returns: 该参与者。
        @raises KeyError: 名册里没有这个名字。
        """
        for player in self.players:
            if player.name == name:
                return player
        raise KeyError(f"名册里没有 {name!r}；有的是 {[p.name for p in self.players]}")


@dataclass
class ParticipantStatus:
    """一个参与者在某一刻的观测结果。"""

    participant: Participant
    #: 本次启动记下的 PID；没起过或已忘记则为 `None`。
    pid: int | None
    #: 探针端口是否在听。
    port_open: bool
    #: 探针报的对局阶段；读不到为 `None`。
    stage: int | None
    #: 当前帧；读不到为 `None`。
    frame: int | None

    @property
    def ready(self) -> bool:
        """是否已经进入对局。"""
        return self.stage == STAGE_INGAME


class MatchHost:
    """整局对局的宿主侧操作。"""

    def __init__(self, roster: MatchRoster, runner=None, probe=None,
                 sleep=time.sleep, now=time.time, dir_of=None):
        """建一个对局宿主。

        @param roster: 名册。
        @param runner: 执行外部命令的可调用对象，默认 `subprocess.run` 的包装。
        @param probe: `(Participant) -> (stage, frame) | None`，默认连探针读状态。
        @param sleep: 休眠函数，测试里替换成假的时钟。
        @param now: 取当前时刻的函数。
        @param dir_of: `(Participant) -> str`，游戏目录在本机的路径；默认由 Windows
            路径推出来，测试里换成临时目录。
        """
        self.roster = roster
        self.runner = runner or default_runner
        self.probe = probe or self._probe_over_socket
        self.sleep = sleep
        self.now = now
        self.dir_of = dir_of or (lambda participant: participant.wsl_dir)
        #: 名册名字 -> 本次启动记下的 PID。进程重启后会丢，那时按可执行文件路径归属。
        self.pids: dict[str, int] = {}

    # ------------------------------------------------------------ 观测
    def _run(self, argv, timeout=COMMAND_TIMEOUT):
        """跑一条外部命令。

        @param argv: 命令与参数。
        @param timeout: 超时秒数。
        @returns: 命令结果。
        """
        return self.runner(argv, timeout=timeout)

    def _probe_over_socket(self, participant: Participant):
        """连该参与者的探针读一帧。

        @param participant: 要读的一方。
        @returns: `(stage, frame)`；连不上返回 `None`。
        """
        from ..engine.client import Client

        try:
            client = Client(port=participant.probe_port)
            client.connect()
            state = client.get_state()
            return state.stage, state.frame
        except Exception:                      # 连不上就是还没起来
            return None

    def _attribute_pids(self) -> dict[str, int]:
        """按可执行文件路径把现有进程归属到各参与者。

        两个参与者的可执行文件同名（第二个目录常与第一个共享硬链接），`tasklist`
        按映像名分不出谁是谁。`Win32_Process` 的 `ExecutablePath` 是各自启动时的
        完整路径，据此归属。进程重启后 `self.pids` 会丢，那时靠这条找回。

        @returns: 名册名字到 PID 的映射，只含确实在跑的参与者。
        """
        script = ("Get-CimInstance Win32_Process "
                  f"-Filter \"Name='{GAME_EXE}'\" | "
                  "ForEach-Object { $_.ProcessId.ToString() + '|' + $_.ExecutablePath }")
        result = self._run([POWERSHELL, "-NoProfile", "-NonInteractive",
                            "-Command", script])
        found: dict[str, int] = {}
        for line in (getattr(result, "stdout", "") or "").splitlines():
            pid_text, _, path = line.strip().partition("|")
            if not pid_text.isdigit() or not path:
                continue
            for participant in self.roster.players:
                expected = f"{participant.game_dir}\\{GAME_EXE}"
                if path.lower() == expected.lower():
                    found.setdefault(participant.name, int(pid_text))
        return found

    def _known_pids(self) -> dict[str, int]:
        """本次启动记下的 PID；没有则按可执行文件路径重新归属。

        @returns: 名册名字到 PID 的映射。
        """
        if self.pids:
            return dict(self.pids)
        attributed = self._attribute_pids()
        if attributed:
            self.pids.update(attributed)
        return attributed

    def status(self) -> list[ParticipantStatus]:
        """逐参与者观测一遍。

        @returns: 每个参与者一项，顺序与名册一致。
        """
        pids = self._known_pids()
        out = []
        for participant in self.roster.players:
            host = self._game_host(participant)
            reading = self.probe(participant)
            stage, frame = reading if reading is not None else (None, None)
            out.append(ParticipantStatus(participant=participant,
                                         pid=pids.get(participant.name),
                                         port_open=host.port_open(),
                                         stage=stage, frame=frame))
        return out

    def _game_host(self, participant: Participant) -> GameHost:
        """为某个参与者建一个 `GameHost`（只用于观测）。

        @param participant: 要观测的一方。
        @returns: 指向该参与者目录与端口的宿主。
        """
        return GameHost(runner=self.runner, port=participant.probe_port,
                        game_dir=participant.game_dir, game_dir_wsl=participant.wsl_dir,
                        crash_report=participant.wsl_dir + "/EXCEPT_CNCNET.TXT")

    # ------------------------------------------------------------ 动作
    def render(self, dry_run: bool = False) -> dict[str, str]:
        """给每一方渲染 `spawn.ini`，返回名字到内容的映射。

        覆盖前把原文件另存为 `.render-bak`——渲染错了还能退回去。名称、阵营、颜色、
        对局端口这些镜像字段全部从名册推导，所以两份不会再各改各的。

        @param dry_run: 只算不写，用来和现有文件逐字对比。
        @returns: 参与者的名字到它那份 `spawn.ini` 内容。
        """
        rendered: dict[str, str] = {}
        for participant in self.roster.players:
            text = render_spawn_ini(participant,
                                    self.roster.peers_of(participant.name),
                                    self.roster.rules)
            rendered[participant.name] = text
            if dry_run:
                continue
            target = pathlib.Path(self.dir_of(participant)) / SPAWN_INI
            if target.exists():
                shutil.copyfile(target, target.with_name(target.name + RENDER_BACKUP_SUFFIX))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        return rendered

    def launch(self) -> dict[str, int]:
        """按名册起全部参与者，返回名字到 PID 的映射。

        相邻两次启动之间隔 `launch_gap` 秒；最后一个起完不额外等待。

        @returns: 本次启动记下的 PID。
        """
        for index, participant in enumerate(self.roster.players):
            if index:
                self.sleep(self.roster.launch_gap)
            self.pids[participant.name] = self._launch_one(participant)
        return dict(self.pids)

    def _launch_one(self, participant: Participant) -> int | None:
        """起一个参与者并记下 PID。

        @param participant: 要起的一方。
        @returns: 进程号；取不到为 `None`。
        """
        script = (f"(Start-Process -FilePath '{participant.game_dir}\\{GAME_EXE}' "
                  f"-ArgumentList '{GAME_ARG}' "
                  f"-WorkingDirectory '{participant.game_dir}' -PassThru).Id")
        result = self._run([POWERSHELL, "-NoProfile", "-NonInteractive",
                            "-Command", script])
        text = (getattr(result, "stdout", "") or "").strip()
        return int(text) if text.isdigit() else None

    def stop(self) -> tuple[int, ...]:
        """停掉各参与者的进程，返回被杀的 PID。

        只按 PID 杀：两个参与者的可执行文件同名，按映像名杀会一次杀掉两个。PID
        从本次启动或按可执行文件路径归属得来，故不会误伤同一台机器上的另一方。

        @returns: 被杀的进程号。
        """
        pids = tuple(pid for pid in self._known_pids().values() if pid is not None)
        for pid in pids:
            self._run([TASKKILL, "/F", "/PID", str(pid)])
        self.pids.clear()
        return pids

    def wait_ready(self, timeout: float | None = None, interval: float = 2.0):
        """等到每个参与者都进入对局。

        `-SPAWN` 不等对手，游戏自己在加载界面等连接，故「进程起来了」不等于
        「可以下令了」——判据只能是每个参与者的探针都报到 `STAGE_INGAME`。

        @param timeout: 等待上限（秒）；默认用名册的 `ready_timeout`。
        @param interval: 两次轮询之间隔多久。
        @returns: 最后的 `status()`；未就绪时也在其中体现。
        @raises TimeoutError: 超时仍有参与者没进对局。
        """
        limit = self.roster.ready_timeout if timeout is None else timeout
        deadline = self.now() + limit
        while True:
            statuses = self.status()
            if all(item.ready for item in statuses):
                return statuses
            if self.now() >= deadline:
                pending = [item.participant.name for item in statuses if not item.ready]
                raise TimeoutError(
                    f"{limit:.0f} 秒内这些参与者没进对局：{pending}；"
                    f"当前 {[(i.participant.name, i.stage) for i in statuses]}")
            self.sleep(interval)
