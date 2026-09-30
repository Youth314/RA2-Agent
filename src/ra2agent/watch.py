"""常驻监听：在玩家 agent 之外盯着局势，出事就把模型叫回来。

**为什么需要单独一个进程**：跑自动层、能发 `Wake` 的那个进程**就是玩家自己的 MCP
服务进程**，而它只在玩家干活时活着——agent 一空闲结算，进程连同事件侦测一起没了。
于是「出事了叫模型」永远只能等它自己醒来才发现：实测两轮，Alpha 掉单位与 Beta
断电都发生在侦测器已经死掉之后。

这个进程不提供工具、不下任何命令，只做三件事：

1. 读局势（只读，与 player 的 MCP 各连一份）；
2. 用**和技法层同一份判据**合成事件、挑出该叫人的那些（`report.watched_only`）；
3. 把唤醒投给指定会话——`--wake-session` 就是 `play_as_*` 返回的 **agent id**。

用法：

    python3 -m ra2agent.watch --player Alpha --wake-session <agent id>

`--player` 从名册里取探针端口，故不用手填端口。
"""
import argparse
import sys
import time

from .autopilot import kind_of
from .client import Client
from .events import summarize
from .match import MatchRoster
from .observation import Observer
from .tactics.builtin.report import watched_only
from .wake import WakeBridge, WakePolicy

#: 读局势的间隔（秒）。与 MCP 侧的 tick 同量级——事件是帧间差，别比游戏还密。
DEFAULT_INTERVAL = 0.5


def wake_text(events):
    """这批事件该叫模型回来看的话，给它一段说明；没有值得说的就给空串。"""
    watched = watched_only(events)
    return summarize(watched) if watched else ""


def session_policy(policy, session):
    """把会话写进策略——唤醒必须点名会话，否则同机两个玩家会叫错人。"""
    import dataclasses
    return dataclasses.replace(policy, session=session)


def watch(port, session, *, interval=DEFAULT_INTERVAL, client=None,
          policy=None, poster=None, on_wake=None, stop_after=None):
    """连上某个游戏实例，盯着事件，出事就投唤醒。返回投递记录列表。

    `stop_after` 给了就跑那么多轮（测试用）；不给就一直跑。
    """
    bridge = WakeBridge(policy=session_policy(policy or WakePolicy(), session),
                        poster=poster)
    if client is None:
        client = Client("127.0.0.1", port)
        client.connect()
    observer = Observer(client).bootstrap()
    cursor = 0
    sent = []
    rounds = 0
    while stop_after is None or rounds < stop_after:
        rounds += 1
        observation = observer.poll()
        fresh, cursor = observer.events.new_since(cursor)
        text = wake_text(fresh)
        if text:
            record = bridge.request(text, observation.frame, tactic="watch")
            sent.append(record)
            if on_wake is not None:
                on_wake(record)
        if stop_after is not None and rounds >= stop_after:
            break
        time.sleep(interval)
    return sent


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="常驻监听：出事唤醒模型")
    parser.add_argument("--roster", default="config/match.json")
    parser.add_argument("--player", required=True, help="名册里的玩家名，如 Alpha")
    parser.add_argument("--wake-session", required=True,
                        help="要唤醒的会话 = play_as_* 返回的 agent id")
    parser.add_argument("--wake-config", default="config/wake.json")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL)
    args = parser.parse_args(argv)

    roster = MatchRoster.load(args.roster)
    participant = roster.get(args.player)
    if participant is None:
        print(f"名册里没有玩家 {args.player}", file=sys.stderr)
        return 2
    policy = WakePolicy.load(args.wake_config)
    print(f"监听 {participant.name}（探针端口 {participant.probe_port}）→ "
          f"会话 {args.wake_session}", flush=True)
    try:
        watch(participant.probe_port, args.wake_session, interval=args.interval,
              policy=policy,
              on_wake=lambda record: print(
                  f"帧 {record['frame']}｜{'已唤醒' if record.get('sent') else '未送达'}"
                  f"｜{record.get('text', '')}"
                  + (f"\n  插件回话：{record['reply']}" if record.get("reply") else "")
                  + (f"\n  失败：{record['error']}" if record.get("error") else ""),
                  flush=True))
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
