#!/usr/bin/env python3
"""命令阶梯测试：从无害到高风险，逐级验证写通道。

  --action SELECT   只调 SelectObject，风险最低
  --action STOP     走 click_mission(Mission_Stop)
  --action MOVE     走 click_mission(Mission_Move)，带坐标

自同步：先等游戏主循环推进（RA2 失焦会暂停），再执行。
"""
import argparse
import sys
import time

sys.path.insert(0, ".")
from ra2client import Client, fields, pb_bytes, pb_uint

GAME_NS = "ra2yrproto.commands."

ACTIONS = {"SELECT": 2, "MOVE": 6, "STOP": 10, "ATTACK_MOVE": 12, "DEPLOY": 1}


def unwrap_state(payload):
    for f, wt, v in fields(payload):
        if f == 1 and wt == 2:
            return v
    return payload


def parse_coords(blob):
    names = {1: "x", 2: "y", 3: "z"}
    return {names[f]: v for f, wt, v in fields(blob) if wt == 0 and f in names}


def parse_state(payload):
    payload = unwrap_state(payload)
    houses, objects, meta = [], [], {}
    for f, wt, v in fields(payload):
        if f == 1 and wt == 0:
            meta["frame"] = v
        elif f == 4 and wt == 2:
            h = {}
            for hf, hwt, hv in fields(v):
                if hf == 2 and hwt == 2:
                    h["name"] = hv.decode(errors="replace")
                elif hf == 5 and hwt == 0:
                    h["current_player"] = bool(hv)
                elif hf == 8 and hwt == 0:
                    h["self"] = hv
            houses.append(h)
        elif f == 6 and wt == 2:
            o = {}
            for of, owt, ov in fields(v):
                if of == 2 and owt == 0:
                    o["health"] = ov
                elif of == 3 and owt == 2:
                    o["coords"] = parse_coords(ov)
                elif of == 4 and owt == 0:
                    o["house"] = ov
                elif of == 10 and owt == 0:
                    o["self"] = ov
                elif of == 13 and owt == 0:
                    o["selected"] = bool(ov)
                elif of == 17 and owt == 2:
                    o["destination"] = parse_coords(ov)
                elif of == 18 and owt == 0:
                    o["mission"] = ov
            objects.append(o)
    return meta, houses, objects


def get_frame(c):
    r = c.send_command(GAME_NS + "GetGameState")
    meta, _, _ = parse_state(r["payload"])
    return meta.get("frame")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", default="SELECT", choices=sorted(ACTIONS))
    ap.add_argument("--dx", type=int, default=1500)
    ap.add_argument("--dy", type=int, default=1500)
    ap.add_argument("--wait", type=int, default=180, help="等待主循环推进的最长秒数")
    a = ap.parse_args()

    c = Client("127.0.0.1", 14521)
    try:
        c.connect()
        print(f"[ok] connected queue_id={c.queue_id}", flush=True)

        print("[..] waiting for game loop to advance (focus the game window)...", flush=True)
        prev = None
        for _ in range(a.wait):
            try:
                f0 = get_frame(c)
            except Exception as exc:
                print(f"[..] read failed ({exc})", flush=True)
                time.sleep(1)
                continue
            if f0 is None:
                time.sleep(1)
                continue
            if prev is not None and f0 > prev:
                print(f"[ok] running (frame {prev} -> {f0})", flush=True)
                break
            prev = f0
            time.sleep(1)
        else:
            print("[!!] game loop never advanced", flush=True)
            return 1

        r = c.send_command(GAME_NS + "GetGameState")
        meta, houses, objects = parse_state(r["payload"])
        me = next((h for h in houses if h.get("current_player")), None)
        mine = [o for o in objects if me and o.get("house") == me.get("self") and "coords" in o]
        print(f"[ok] frame={meta.get('frame')} me={me.get('name') if me else None} mine={len(mine)}", flush=True)
        if not mine:
            print("[!!] no owned object", flush=True)
            return 1

        t = mine[0]
        print(f"[..] target self={t['self']:#x} coords={t.get('coords')} "
              f"mission={t.get('mission')} selected={t.get('selected')}", flush=True)

        order = pb_uint(1, t["self"]) + pb_uint(2, ACTIONS[a.action])
        if a.action in ("MOVE", "ATTACK_MOVE"):
            c0 = t["coords"]
            coords = pb_uint(1, c0["x"] + a.dx) + pb_uint(2, c0["y"] + a.dy) + pb_uint(3, c0.get("z", 0))
            order += pb_bytes(4, coords)
            print(f"[..] target cell offset (+{a.dx}, +{a.dy})", flush=True)

        print(f"[..] sending UnitOrder action={a.action}({ACTIONS[a.action]})", flush=True)
        res = c.send_command(GAME_NS + "UnitOrder", order)
        print(f"[ok] result type={res['type']} code={res['code']} err={res['error']!r}", flush=True)

        for i in range(5):
            time.sleep(1)
            r2 = c.send_command(GAME_NS + "GetGameState")
            m2, _, objs2 = parse_state(r2["payload"])
            after = next((o for o in objs2 if o.get("self") == t["self"]), None)
            if not after:
                print(f"[{i}] frame={m2.get('frame')} target GONE", flush=True)
                continue
            print(f"[{i}] frame={m2.get('frame')} coords={after.get('coords')} "
                  f"mission={after.get('mission')} selected={after.get('selected')} "
                  f"dest={after.get('destination')}", flush=True)

        print("\n===== SURVIVED (no crash) =====", flush=True)
        return 0
    finally:
        try:
            c.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
