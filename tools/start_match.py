#!/usr/bin/env python3
"""整局对局的命令行入口：起、看、停。

`-SPAWN` 不进大厅也不等对手，游戏自己在加载界面等连接，所以**只起一个实例**的
后果是它在加载界面干等约 60 秒再判对方掉线。起局要按名册一次起全，判据也只能是
每个参与者都进了对局，而不是「进程起来了」。

用法：

```sh
python3 tools/start_match.py up        # 按名册起全，等到都进对局
python3 tools/start_match.py status    # 逐参与者看进程、端口、阶段、帧
python3 tools/start_match.py down      # 按 PID 停（不会误伤另一方）
```

名册在 `config/match.json`；加参与者改那里，不加命令行参数——目录与端口是部署
事实，不是每次命令行的临时选择。
"""
import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ra2agent.match import MatchHost, MatchRoster  # noqa: E402

#: 名册位置。
ROSTER = REPO / "config" / "match.json"


def describe(status) -> str:
    """把一个参与者的观测结果写成一行。

    @param status: `ParticipantStatus`。
    @returns: 给人看的单行描述。
    """
    stage = "—" if status.stage is None else str(status.stage)
    frame = "—" if status.frame is None else str(status.frame)
    pid = "—" if status.pid is None else str(status.pid)
    return (f"  {status.participant.name:<8} pid={pid:<8} "
            f"端口={'通' if status.port_open else '不通':<4} "
            f"stage={stage:<3} frame={frame:<7} "
            f"{'就绪' if status.ready else ''}")


def cmd_up(host: MatchHost) -> int:
    """起整局并等到都进对局。

    @param host: 对局宿主。
    @returns: 进程退出码。
    """
    print("按名册启动：")
    pids = host.launch()
    for name, pid in pids.items():
        print(f"  {name:<8} pid={pid if pid is not None else '取不到'}")
    print(f"\n等全部进入对局（上限 {host.roster.ready_timeout:.0f} 秒）…")
    try:
        statuses = host.wait_ready()
    except TimeoutError as exc:
        print(f"未就绪：{exc}", file=sys.stderr)
        for status in host.status():
            print(describe(status))
        return 1
    print("都进对局了：")
    for status in statuses:
        print(describe(status))
    return 0


def cmd_status(host: MatchHost) -> int:
    """逐参与者看状态。

    @param host: 对局宿主。
    @returns: 都就绪返回 0，否则 1。
    """
    statuses = host.status()
    for status in statuses:
        print(describe(status))
    return 0 if all(item.ready for item in statuses) else 1


def cmd_down(host: MatchHost) -> int:
    """停掉整局。

    @param host: 对局宿主。
    @returns: 进程退出码。
    """
    pids = host.stop()
    print(f"已停 {len(pids)} 个进程：{list(pids)}" if pids else "没有在跑的参与者")
    return 0


def main(argv: list[str] | None = None) -> int:
    """命令行入口。

    @param argv: 参数列表，默认取 `sys.argv`。
    @returns: 进程退出码。
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["up", "status", "down"],
                        help="up 起整局并等就绪；status 看状态；down 停整局")
    parser.add_argument("--roster", type=pathlib.Path, default=ROSTER,
                        help="名册路径，默认 config/match.json")
    args = parser.parse_args(argv)

    try:
        roster = MatchRoster.load(args.roster)
    except (OSError, ValueError) as exc:
        print(f"名册读不了：{exc}", file=sys.stderr)
        return 2

    host = MatchHost(roster)
    return {"up": cmd_up, "status": cmd_status, "down": cmd_down}[args.action](host)


if __name__ == "__main__":
    raise SystemExit(main())
