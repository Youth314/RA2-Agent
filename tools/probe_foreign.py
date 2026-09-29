#!/usr/bin/env python3
"""探测越权指挥与事件归属伪造。

回答两个问题：

1. 命令通道是否检查单位归属——能否给敌方单位下达指令？
2. `AddEvent` 的 `spoof=true` 能否把生产事件归属到别的阵营？

第 2 项会构造伪帧号的事件，风险高于第 1 项，故默认不跑，需 `--spoof` 显式开启。

用法:
    python3 probe_foreign.py            # 只测越权指挥
    python3 probe_foreign.py --spoof    # 另测事件归属伪造
"""
import argparse
import json
import sys
import time
from pathlib import Path

import batchkit
from ra2agent import payloads
from ra2agent.client import Client
from ra2agent.constants import AbstractType, Mission, NetworkEvent, UnitAction

OUT_DIR = Path(__file__).resolve().parent.parent / ".agents" / "tmp"
COMBAT_TYPES = (AbstractType.UNIT, AbstractType.INFANTRY)


def wait_mission(client, pointer, mission, polls=150):
    """轮询直到对象的 mission 变为给定值，返回帧号；未变返回 None。"""
    for _ in range(polls):
        state = client.get_state()
        obj = state.object(pointer)
        if obj is not None and obj.mission == mission:
            return state.frame
        time.sleep(0.01)
    return None


def probe_foreign_command(client, result):
    """给敌方单位下一条 STOP，看引擎是否执行。"""
    state = client.get_state()
    me = state.player_house()
    hostile = {h.pointer for h in state.enemy_houses()}
    targets = [o for o in state.objects
               if o.house in hostile and o.object_type in COMBAT_TYPES
               and not o.in_limbo]
    if not targets:
        result["foreign_command"] = {"status": "skip", "reason": "没有敌方作战单位"}
        return

    target = targets[0]
    before = target.mission
    start_frame = state.frame
    reply = client.unit_order([target], UnitAction.STOP)
    changed = wait_mission(client, target.pointer, Mission.STOP)

    result["foreign_command"] = {
        "status": "controlled" if changed is not None else "refused",
        "target_pointer": target.pointer,
        "target_house": target.house,
        "my_house": me.pointer,
        "mission_before": int(before),
        "mission_before_name": Mission(before).name if before in set(Mission) else before,
        "mission_after": int(Mission.STOP),
        "start_frame": start_frame,
        "changed_frame": changed,
        "result_code": reply.code,
        "error": reply.error,
        "note": ("引擎不检查归属，敌方单位接受了指令"
                 if changed is not None else
                 "敌方单位未改变 mission，可能被引擎拒绝或需要更长时间"),
    }


def probe_spoofed_production(client, result, types):
    """用 spoof=true 把生产事件归属到敌方阵营。"""
    state = client.get_state()
    hostiles = state.enemy_houses()
    if not hostiles:
        result["spoofed_production"] = {"status": "skip", "reason": "没有敌方阵营"}
        return
    enemy = hostiles[0]
    entry = types.find("Power Plant", rtti=AbstractType.BUILDINGTYPE)
    if entry is None:
        result["spoofed_production"] = {"status": "skip", "reason": "找不到发电厂类型"}
        return

    before_money = enemy.money
    before_factories = len(state.factories)
    reply = client.add_event(NetworkEvent.PRODUCE,
                             production=(entry.type, entry.array_index),
                             spoof=True, house_index=enemy.array_index)

    factories, money = [], None
    for _ in range(100):
        state = client.get_state()
        enemy_now = next((h for h in state.houses if h.pointer == enemy.pointer), None)
        money = enemy_now.money if enemy_now else None
        factories = [f for f in state.factories if f.owner == enemy.pointer]
        if factories:
            break
        time.sleep(0.05)

    result["spoofed_production"] = {
        "status": "accepted" if factories else "no_effect",
        "enemy_house": enemy.pointer,
        "enemy_array_index": enemy.array_index,
        "house_is_neutral": enemy.is_neutral,
        "type": entry.name,
        "result_code": reply.code,
        "error": reply.error,
        "factories_before": before_factories,
        "enemy_factories_after": [
            {"object": f.object, "timer": f.progress_timer,
             "completed": f.completed} for f in factories],
        "enemy_money_before": before_money,
        "enemy_money_after": money,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=14521)
    parser.add_argument("--spoof", action="store_true",
                        help="另测事件归属伪造（构造伪帧号，风险较高）")
    parser.add_argument("--no-focus", action="store_true")
    args = parser.parse_args()

    result = {}

    def body():
        client = Client(args.host, args.port)
        client.connect()
        try:
            types = client.read_object_types()
            probe_foreign_command(client, result)
            if args.spoof:
                probe_spoofed_production(client, result, types)
        finally:
            client.close()

    if args.no_focus:
        body()
    else:
        with batchkit.focused_batch("越权探测"):
            body()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "probe-foreign.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n结果已写入 {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
