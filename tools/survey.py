#!/usr/bin/env python3
"""命令能力测绘：跑实测项并把结果写成 JSON。

依据 .agents/notes/引擎/命令能力测绘计划.md。结果写入 .agents/tmp/survey-<组>.json。

用法:
    python3 survey.py timing      # 甲组：往返耗时、生效延迟、错误通道
    python3 survey.py batch       # 乙组：合法坐标移动、多单位同令、命令速率、批量上限
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import batchkit
from ra2client import (NS, Client, InvalidCommand, MISSION_NAMES, UA_CAPTURE,
                       UA_DEPLOY, UA_MOVE, UA_SELL, UA_SELL_CELL, UA_STOP, UA_UNSELECT,
                       Validator,
                       fmap, parse_coordinates, pb_bytes, pb_uint)

OUT_DIR = Path(__file__).resolve().parent.parent / ".agents" / "tmp"

LEPTONS = 256
MISSION_MOVE, MISSION_GUARD, MISSION_STOP = 2, 5, 13
LAND_CLEAR = 0

# UnitAction 常量
UA_ATTACK = 8


def order_payload(addresses, action, target_object=0, coordinates=None):
    out = b"".join(pb_uint(1, a) for a in addresses) + pb_uint(2, action)
    if target_object:
        out += pb_uint(3, target_object)
    if coordinates is not None:
        out += pb_bytes(4, pb_uint(1, coordinates[0])
                        + pb_uint(2, coordinates[1]) + pb_uint(3, 0))
    return out


def pick_idle_unit(state, object_type=1):
    """挑一个己方、非 limbo、mission 为 Guard 的单位。"""
    for o in state.own_objects():
        if (not o["in_limbo"] and o["mission"] == MISSION_GUARD
                and o["object_type"] == object_type):
            return o
    return None


def find_free_cell(md, cx, cy, radius=6):
    """在 (cx,cy) 附近找一块已探明且为 Clear 的格子。"""
    best = None
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx == 0 and dy == 0:
                continue
            x, y = cx + dx, cy + dy
            if not (0 <= x < md.width and 0 <= y < md.height):
                continue
            if md.shrouded(x, y):
                continue
            if md.columns["land_type"][md.cell_index(x, y)] != LAND_CLEAR:
                continue
            d = dx * dx + dy * dy
            if best is None or d < best[0]:
                best = (d, x, y)
    return (best[1], best[2]) if best else None


def wait_until(c, pred, max_polls=200):
    """轮询状态直到 pred(state) 为真。返回 (state, 轮询次数)。"""
    for i in range(max_polls):
        s = c.get_state()
        if pred(s):
            return s, i + 1
    return None, max_polls


# ------------------------------------------------------------------ 校验层自测
def local_validator_tests(state, md, res):
    """纯本地：校验层必须拦下会崩游戏或必然失败的输入，且不误拒合法输入。"""
    v = Validator(md)
    cases = []

    def expect_reject(name, fn):
        try:
            fn()
        except InvalidCommand as e:
            cases.append({"case": name, "rejected": True, "message": str(e)})
        else:
            cases.append({"case": name, "rejected": False})

    def expect_accept(name, fn):
        try:
            fn()
        except InvalidCommand as e:
            cases.append({"case": name, "accepted": False, "message": str(e)})
        else:
            cases.append({"case": name, "accepted": True})

    limit_x = md.width * LEPTONS
    limit_y = md.height * LEPTONS
    expect_accept("地图内中心点", lambda: v.check_coordinates(limit_x // 2, limit_y // 2))
    expect_reject("x 刚好越界", lambda: v.check_coordinates(limit_x, 1000))
    expect_reject("y 刚好越界", lambda: v.check_coordinates(1000, limit_y))
    expect_reject("x 极大(short 回绕)", lambda: v.check_coordinates(10_000_000, 1000))
    expect_reject("x 为负", lambda: v.check_coordinates(-1, 1000))
    expect_reject("未实现的 action", lambda: v.check_action(UA_UNSELECT))
    expect_reject("对象不存在",
                  lambda: v.check_objects(state, [0xDEADBEEF]))
    expect_reject("MOVE 缺坐标",
                  lambda: v.check_unit_order(state, [state.own_objects()[0]["self"]],
                                             UA_MOVE, coordinates=None))
    expect_reject("CAPTURE 缺目标",
                  lambda: v.check_unit_order(state, [state.own_objects()[0]["self"]],
                                             UA_CAPTURE, target_object=0))

    rejects = [c for c in cases if "rejected" in c]
    accepts = [c for c in cases if "accepted" in c]
    res["validator"] = {
        "status": "pass" if (all(c["rejected"] for c in rejects)
                             and all(c["accepted"] for c in accepts)) else "fail",
        "cases": cases,
    }


# ------------------------------------------------------------------ 甲组
def test_rt_latency(c, res):
    """同步命令的往返耗时，用于执行器节奏设计。"""
    samples = []
    for _ in range(20):
        t0 = time.perf_counter()
        c.get_state()
        samples.append((time.perf_counter() - t0) * 1000.0)
    res["rt"] = {
        "op": "GetGameState",
        "n": len(samples),
        "min_ms": round(min(samples), 2),
        "median_ms": round(statistics.median(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def test_16_latency(c, res):
    """下令到状态一致经过多少帧。"""
    st = c.get_state()
    unit = pick_idle_unit(st)
    if unit is None:
        res["16"] = {"status": "skip", "reason": "没有 Guard 状态的己方单位"}
        return
    target = unit["self"]
    start_frame = st.frame
    c.send_async(NS + "UnitOrder", order_payload([target], UA_STOP))

    trace, changed = [], None
    for _ in range(150):
        s = c.get_state()
        o = s.object(target)
        mission = o["mission"] if o else None
        trace.append([s.frame, mission])
        if mission == MISSION_STOP:
            changed = s.frame
            break
    res["16"] = {
        "status": "pass" if changed is not None else "fail",
        "object": target,
        "start_frame": start_frame,
        "changed_frame": changed,
        "delay_frames": (changed - start_frame) if changed is not None else None,
        "polls_used": len(trace),
        "trace": trace[:15],
    }


def test_17_error_channel(c, res):
    """未实现的 action 与不存在的对象如何报错，状态是否保持不变。"""
    st = c.get_state()
    unit = pick_idle_unit(st) or (st.own_objects() or [None])[0]
    if unit is None:
        res["17"] = {"status": "skip", "reason": "没有己方单位"}
        return
    target = unit["self"]

    before = c.get_state().object(target)["mission"]
    bad = c.send_command(NS + "UnitOrder", order_payload([target], UA_UNSELECT))
    after = c.get_state().object(target)["mission"]
    ghost = c.send_command(NS + "UnitOrder", order_payload([0xDEADBEEF], UA_STOP))

    res["17"] = {
        "status": "pass",
        "unimplemented_action": {
            "action": "UNSELECT(3)",
            "result_code": bad["code"],
            "error_message": bad["error"],
            "mission_before": before,
            "mission_after": after,
            "state_unchanged": before == after,
        },
        "missing_object": {
            "pointer": "0xDEADBEEF",
            "result_code": ghost["code"],
            "error_message": ghost["error"],
        },
    }


def run_timing(c):
    st = c.get_state()
    md = c.read_map()
    c.validator = Validator(md)
    res = {"map": {"width": md.width, "height": md.height}}
    local_validator_tests(st, md, res)
    test_rt_latency(c, res)
    test_16_latency(c, res)
    test_17_error_channel(c, res)
    return res


# ------------------------------------------------------------------ 乙组
def test_10_move(c, res):
    """带合法坐标的移动：校验层放行，且引擎真的执行。"""
    st = c.get_state()
    unit = pick_idle_unit(st)
    if unit is None:
        res["10"] = {"status": "skip", "reason": "没有 Guard 状态的己方载具"}
        return
    md = c.read_map()
    c.validator = Validator(md)
    cx = unit["coordinates"]["x"] // LEPTONS
    cy = unit["coordinates"]["y"] // LEPTONS
    tgt = find_free_cell(md, cx, cy, radius=6)
    if tgt is None:
        res["10"] = {"status": "skip", "reason": "附近找不到已探明的 Clear 格子"}
        return
    world = (tgt[0] * LEPTONS + LEPTONS // 2, tgt[1] * LEPTONS + LEPTONS // 2)

    try:
        c.validator.check_coordinates(*world)
    except InvalidCommand as e:
        res["10"] = {"status": "fail", "reason": f"校验层误拒合法坐标: {e}"}
        return

    start_frame = st.frame
    c.send_async(NS + "UnitOrder",
                 order_payload([unit["self"]], UA_MOVE, coordinates=world))
    s, polls = wait_until(
        c, lambda s: (s.object(unit["self"]) or {}).get("mission") == MISSION_MOVE,
        max_polls=150)
    after = c.get_state().object(unit["self"])
    res["10"] = {
        "status": "pass" if s is not None else "fail",
        "object": unit["self"],
        "from_cell": [cx, cy],
        "target_cell": list(tgt),
        "start_frame": start_frame,
        "mission": after["mission"] if after else None,
        "mission_name": MISSION_NAMES.get(after["mission"]) if after else None,
        "destination": after["destination"] if after else None,
        "polls_used": polls,
    }


def test_13_multi(c, res):
    """一条命令作用于多个对象。"""
    st = c.get_state()
    units = [o for o in st.own_objects()
             if o["object_type"] == 1 and not o["in_limbo"]
             and o["mission"] == MISSION_GUARD]
    if len(units) < 2:
        res["13"] = {"status": "skip", "reason": f"Guard 状态载具不足（{len(units)}）"}
        return
    addrs = [u["self"] for u in units]
    c.send_async(NS + "UnitOrder", order_payload(addrs, UA_STOP))
    s, polls = wait_until(
        c, lambda s: all((s.object(a) or {}).get("mission") == MISSION_STOP
                         for a in addrs), max_polls=150)
    missions = {a: (c.get_state().object(a) or {}).get("mission") for a in addrs}
    res["13"] = {
        "status": "pass" if s is not None else "fail",
        "count": len(addrs),
        "addresses": addrs,
        "missions": missions,
        "all_stopped": all(m == MISSION_STOP for m in missions.values()),
        "polls_used": polls,
    }


def test_15_rate(c, res):
    """同一帧内连发多条命令，结果是否全部回传。"""
    st = c.get_state()
    unit = pick_idle_unit(st) or (st.own_objects() or [None])[0]
    if unit is None:
        res["15"] = {"status": "skip", "reason": "没有己方单位"}
        return
    target = unit["self"]

    n = 20
    sent = []
    t0 = time.perf_counter()
    for _ in range(n):
        ack = c.send_async(NS + "UnitOrder", order_payload([target], UA_STOP))
        sent.append(ack.get("id"))
    elapsed = time.perf_counter() - t0

    got, deadline = [], time.time() + 5.0
    while time.time() < deadline and len(got) < n:
        got.extend(c.poll_all(poll_timeout_ms=500))
    ids = {g["id"] for g in got}
    res["15"] = {
        "status": "pass" if len(ids & set(sent)) == n else "partial",
        "sent_count": n,
        "send_elapsed_ms": round(elapsed * 1000, 1),
        "results_total": len(got),
        "results_matched": len(ids & set(sent)),
        "lost": sorted(set(sent) - ids),
        "errors": [g["error"] for g in got if g["code"]],
    }


def test_14_bulk(c, res):
    """一条命令携带大量对象地址时的行为。"""
    st = c.get_state()
    unit = pick_idle_unit(st) or (st.own_objects() or [None])[0]
    if unit is None:
        res["14"] = {"status": "skip", "reason": "没有己方单位"}
        return
    target = unit["self"]
    out = []
    for n in (10, 50, 200, 500):
        payload = order_payload([target] * n, UA_STOP)
        t0 = time.perf_counter()
        r = c.send_command(NS + "UnitOrder", payload, poll_timeout=8000)
        ms = (time.perf_counter() - t0) * 1000
        out.append({
            "addresses": n,
            "payload_bytes": len(payload),
            "result_type": r["type"],
            "result_code": r["code"],
            "error": r["error"][:120],
            "elapsed_ms": round(ms, 1),
        })
        if r["type"] == "POLL_TIMEOUT":
            break
    res["14"] = {"status": "pass", "trials": out}


def run_batch(c):
    st = c.get_state()
    md = c.read_map()
    c.validator = Validator(md)
    res = {"map": {"width": md.width, "height": md.height}}
    local_validator_tests(st, md, res)
    test_10_move(c, res)
    test_13_multi(c, res)
    test_15_rate(c, res)
    test_14_bulk(c, res)
    return res


# ------------------------------------------------------------------ 丁组
def test_26_add_message(c, res):
    """游戏内文本提示通道，可用于向人展示 Agent 意图。"""
    r = c.add_message("RA2 Agent: 消息通道测试", duration_frames=300)
    res["26"] = {
        "status": "pass" if not r["code"] else "fail",
        "result_type": r["type"],
        "result_code": r["code"],
        "error": r["error"],
    }


def test_04_deploy(c, res, types):
    """部署：基地车变建筑。

    判据不能盯着原 `pointer_self`：部署会销毁载具、另建一个建筑对象，指针改变。
    改为比对部署前后的己方建筑集合。
    """
    st = c.get_state()
    before_buildings = {o["self"] for o in st.own_objects() if o["object_type"] == 6}
    cands = [o for o in st.own_objects()
             if o["object_type"] == 1 and not o["in_limbo"] and not o["deployed"]]
    if not cands:
        res["4"] = {"status": "skip", "reason": "没有未部署的己方载具"}
        return
    mcv = max(cands, key=lambda o: o["health"])
    before = {
        "name": types.name(mcv),
        "self": mcv["self"],
        "health": mcv["health"],
        "object_type": mcv["object_type"],
        "mission": mcv["mission"],
        "own_buildings": sorted(before_buildings),
    }

    def changed(s):
        old = s.object(mcv["self"])
        new_b = [o for o in s.own_objects()
                 if o["object_type"] == 6 and o["self"] not in before_buildings]
        return bool(new_b) or (old is not None and old["deployed"])

    c.send_async(NS + "UnitOrder", order_payload([mcv["self"]], UA_DEPLOY))
    s, polls = wait_until(c, changed, max_polls=200)

    after = c.get_state()
    new_b = [o for o in after.own_objects()
             if o["object_type"] == 6 and o["self"] not in before_buildings]
    res["4"] = {
        "status": "pass" if s is not None else "fail",
        "before": before,
        "source_pointer_still_present": after.object(mcv["self"]) is not None,
        "new_buildings": [{"self": o["self"], "name": types.name(o),
                           "health": o["health"],
                           "cell": [o["coordinates"]["x"] // LEPTONS,
                                    o["coordinates"]["y"] // LEPTONS]}
                          for o in new_b],
        "polls_used": polls,
    }


def test_24_mission_clicked(c, res):
    """MissionClicked 与 UnitOrder 的关系，哪个的错误信号更可靠。"""
    st = c.get_state()
    unit = pick_idle_unit(st)
    if unit is None:
        res["24"] = {"status": "skip", "reason": "没有 Guard 状态的己方载具"}
        return
    md = c.read_map()
    c.validator = Validator(md)
    cx = unit["coordinates"]["x"] // LEPTONS
    cy = unit["coordinates"]["y"] // LEPTONS
    tgt = find_free_cell(md, cx, cy, radius=6)
    if tgt is None:
        res["24"] = {"status": "skip", "reason": "附近找不到合法格子"}
        return
    wx, wy = tgt[0] * LEPTONS + LEPTONS // 2, tgt[1] * LEPTONS + LEPTONS // 2
    try:
        c.validator.check_coordinates(wx, wy)
    except InvalidCommand as e:
        res["24"] = {"status": "fail", "reason": f"校验层误拒: {e}"}
        return

    payload = (pb_uint(1, unit["self"]) + pb_uint(2, MISSION_MOVE)
               + pb_bytes(4, pb_uint(1, wx) + pb_uint(2, wy)))
    r = c.send_command(NS + "MissionClicked", payload, poll_timeout=8000)
    s, polls = wait_until(
        c, lambda s: (s.object(unit["self"]) or {}).get("mission") == MISSION_MOVE,
        max_polls=150)
    res["24"] = {
        "status": "pass" if s is not None else "fail",
        "object": unit["self"],
        "target_cell": list(tgt),
        "result_type": r["type"],
        "result_code": r["code"],
        "error": r["error"][:120],
        "mission_reached_move": s is not None,
        "polls_used": polls,
    }


def run_engage(c):
    res = {}
    types = c.read_object_types()
    test_26_add_message(c, res)
    test_04_deploy(c, res, types)
    test_24_mission_clicked(c, res)
    return res


# ------------------------------------------------------------------ 观测与配置
def measure_frames(c, n=40):
    """统计连续 n 帧的 GameState 体积与增量格子数。"""
    sizes, cells = [], []
    for _ in range(n):
        st = c.get_state()
        sizes.append(len(st.raw))
        cells.append(len(st.cells_difference))
    return {
        "n": n,
        "payload_min": min(sizes),
        "payload_median": int(statistics.median(sizes)),
        "payload_max": max(sizes),
        "payload_mean": round(statistics.mean(sizes), 1),
        "cells_diff_max": max(cells),
        "cells_diff_mean": round(statistics.mean(cells), 1),
    }


def test_27_config(c, res):
    """配置读写，以及地图解析间隔对单帧体积的影响。"""
    entry = {"before": c.inspect_config()}

    st = c.get_state()
    entry["objects"] = len(st.objects)
    entry["houses"] = len(st.houses)
    entry["frames_before"] = measure_frames(c, 40)

    t0 = time.perf_counter()
    md = c.read_map()
    entry["read_map"] = {
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "bytes": len(md.raw),
        "width": md.width,
        "height": md.height,
        "cells": len(md.columns.get("shrouded", [])),
    }

    entry["after_set_1000"] = c.update_config(parse_map_data_interval=1000)
    entry["frames_interval_1000"] = measure_frames(c, 40)

    entry["restored"] = c.update_config(parse_map_data_interval=1)
    entry["frames_interval_1"] = measure_frames(c, 40)

    # 源码称 0 会被强制改回 1，实测确认
    entry["set_zero_effective"] = c.update_config(
        parse_map_data_interval=0)["parse_map_data_interval"]

    entry["status"] = "pass"
    res["27"] = entry


def run_observe(c):
    res = {}
    test_27_config(c, res)
    return res


# ------------------------------------------------------------------ 丙组
BUILDINGTYPE = 7
PRODUCE_BEGIN = 1
PLACE_QUERY_MAX = 1024

BUILD_CANDIDATES = ["Power Plant", "Ore Refinery", "Barracks", "War Factory",
                    "Pillbox", "Patriot Missile", "Battle Lab", "Service Depot"]


def find_type(types, needle, rtti=BUILDINGTYPE):
    """按名字子串找可建造（cost>0）的类型。"""
    for e in types.by_pointer.values():
        if (e["type"] == rtti and e["cost"] > 0
                and needle.lower() in e["name"].lower()):
            return e
    return None


def object_type_payload(e):
    """`ObjectTypeClass` 的最小字段集：服务端只用 array_index、pointer_self、type。"""
    return (pb_uint(5, e["array_index"]) + pb_uint(6, e["pointer_self"])
            + pb_uint(9, e["type"]))


def own_factories(state):
    house = state.player_house()
    return [f for f in state.factories if f["owner"] == house["self"]]


def test_build(c, res, types):
    """生产一个建筑并放置：ProduceOrder → 等完工 → PlaceQuery → PlaceBuilding。

    两处必须注意：`PlaceQuery.house_class` 传 0 不会被当成当前玩家（proto 注释
    与实现不符），必须给真实 House 指针；命令失败时响应 payload 是请求的回声而
    非结果，解析前必须先看 `result_code`。
    """
    entry = {}
    e = find_type(types, "Power Plant")
    if e is None:
        res["build"] = {"status": "fail", "note": "找不到 Allied Power Plant"}
        return
    entry["type"] = {"name": e["name"], "cost": e["cost"],
                     "array_index": e["array_index"]}

    # --- 1. 取得一个已完工待放置的建筑 ---
    done = [f for f in own_factories(c.get_state()) if f["completed"]]
    if done:
        entry["produce"] = {"reused": True}
        building_ptr = done[0]["object"]
    else:
        payload = pb_bytes(1, object_type_payload(e)) + pb_uint(2, PRODUCE_BEGIN)
        r = c.send_command(NS + "ProduceOrder", payload, poll_timeout=10000)
        entry["produce"] = {"reused": False, "result_code": r["code"],
                            "error": r["error"][:160]}
        if r["code"]:
            entry["status"] = "fail"
            res["build"] = entry
            return
        trace, done_state = [], None
        for _ in range(400):
            s = c.get_state()
            mine = own_factories(s)
            trace.append([s.frame] + [[f["object"], f["progress_timer"],
                                       f["completed"]] for f in mine])
            if any(f["completed"] for f in mine):
                done_state = s
                break
            time.sleep(0.15)
        if done_state is None:
            entry["status"] = "partial"
            entry["note"] = "生产未在观察窗口内完成"
            entry["progress_last"] = trace[-1] if trace else None
            res["build"] = entry
            return
        entry["progress_samples"] = len(trace)
        entry["progress_first"] = trace[0]
        entry["progress_last"] = trace[-1]
        building_ptr = next(f for f in own_factories(done_state)
                            if f["completed"])["object"]
    entry["building_ptr"] = building_ptr

    # --- 2. PlaceQuery，house_class 给真实指针 ---
    st = c.get_state()
    house = st.player_house()
    md = c.read_map()
    sites = [o for o in st.own_objects() if o["object_type"] == 6]
    if not sites:
        entry["status"] = "partial"
        entry["note"] = "没有己方建筑可作为候选中心"
        res["build"] = entry
        return
    bcx = sites[0]["coordinates"]["x"] // LEPTONS
    bcy = sites[0]["coordinates"]["y"] // LEPTONS

    candidates = []
    for dy in range(-10, 11):
        for dx in range(-10, 11):
            x, y = bcx + dx, bcy + dy
            if 0 <= x < md.width and 0 <= y < md.height:
                candidates.append((x * LEPTONS + LEPTONS // 2,
                                   y * LEPTONS + LEPTONS // 2))

    pq = pb_uint(1, e["pointer_self"]) + pb_uint(2, house["self"])
    for wx, wy in candidates[:PLACE_QUERY_MAX]:
        pq += pb_bytes(3, pb_uint(1, wx) + pb_uint(2, wy))
    r = c.send_command(NS + "PlaceQuery", pq, poll_timeout=20000)

    legal = []
    if not r["code"]:
        legal = [parse_coordinates(v)
                 for _, v in fmap(r["payload"]).get(3, [])]
    entry["place_query"] = {
        "candidates_sent": len(candidates[:PLACE_QUERY_MAX]),
        "result_code": r["code"], "error": r["error"][:160],
        "legal_count": len(legal), "first_legal": legal[:3],
    }

    # 对照：house_class=0 是否被当成当前玩家（源码：不会）
    pq0 = pb_uint(1, e["pointer_self"])
    for wx, wy in candidates[:PLACE_QUERY_MAX]:
        pq0 += pb_bytes(3, pb_uint(1, wx) + pb_uint(2, wy))
    r0 = c.send_command(NS + "PlaceQuery", pq0, poll_timeout=20000)
    entry["place_query_zero_house"] = {"result_code": r0["code"],
                                       "error": r0["error"][:160]}

    if not legal:
        entry["status"] = "partial"
        entry["note"] = "PlaceQuery 未返回合法坐标"
        res["build"] = entry
        return

    # --- 3. 放置，逐个候选重试 ---
    placed, attempts = [], []
    for spot in legal[:8]:
        payload = (pb_bytes(1, pb_uint(10, building_ptr))
                   + pb_bytes(2, pb_uint(1, spot["x"]) + pb_uint(2, spot["y"])))
        rr = c.send_command(NS + "PlaceBuilding", payload, poll_timeout=15000)
        attempts.append({"cell": [spot["x"] // LEPTONS, spot["y"] // LEPTONS],
                         "result_code": rr["code"], "error": rr["error"][:120]})
        if not rr["code"]:
            time.sleep(0.5)
            after = c.get_state()
            placed = [o for o in after.own_objects()
                      if o["object_type"] == 6
                      and o["self"] not in {s["self"] for s in sites}]
            if placed:
                break
    entry["place_attempts"] = attempts
    entry["placed"] = [{"self": o["self"], "name": types.name(o),
                        "cell": [o["coordinates"]["x"] // LEPTONS,
                                 o["coordinates"]["y"] // LEPTONS]}
                       for o in placed]

    # --- 4. 非法放置：远离所有己方建筑的格子 ---
    far = ((md.width - 2) * LEPTONS, (md.height - 2) * LEPTONS)
    payload = (pb_bytes(1, pb_uint(10, building_ptr))
               + pb_bytes(2, pb_uint(1, far[0]) + pb_uint(2, far[1])))
    r3 = c.send_command(NS + "PlaceBuilding", payload, poll_timeout=15000)
    entry["illegal_place"] = {"coordinates": list(far), "result_code": r3["code"],
                              "error": r3["error"][:200]}

    entry["status"] = "pass" if placed else "partial"
    res["build"] = entry


def run_build(c):
    res = {}
    types = c.read_object_types()
    test_build(c, res, types)
    return res


# ------------------------------------------------------------------ 收尾组
def produce_one(c, types, name="Power Plant", wait_frames=400):
    """生产一个建筑并等完工。返回 (待放置对象指针, 类型条目, 错误信息)。"""
    e = find_type(types, name)
    if e is None:
        return None, None, f"找不到 {name}"
    payload = pb_bytes(1, object_type_payload(e)) + pb_uint(2, PRODUCE_BEGIN)
    r = c.send_command(NS + "ProduceOrder", payload, poll_timeout=10000)
    if r["code"]:
        return None, e, r["error"][:160]
    for _ in range(wait_frames):
        s = c.get_state()
        done = [f for f in own_factories(s) if f["completed"]]
        if done:
            return done[0]["object"], e, None
        time.sleep(0.15)
    return None, e, "生产未在观察窗口内完成"


def test_23_illegal_place(c, res, types):
    """非法位置放置如何报错，且建筑是否仍可合法放置。"""
    ptr, e, err = produce_one(c, types)
    if ptr is None:
        res["23"] = {"status": "skip", "reason": err}
        return
    md = c.read_map()
    far = ((md.width - 2) * LEPTONS, (md.height - 2) * LEPTONS)
    payload = (pb_bytes(1, pb_uint(10, ptr))
               + pb_bytes(2, pb_uint(1, far[0]) + pb_uint(2, far[1])))
    r = c.send_command(NS + "PlaceBuilding", payload, poll_timeout=15000)

    # 非法失败后，同一对象仍应能合法放置
    st = c.get_state()
    house = st.player_house()
    sites = [o for o in st.own_objects() if o["object_type"] == 6]
    bcx = sites[0]["coordinates"]["x"] // LEPTONS
    bcy = sites[0]["coordinates"]["y"] // LEPTONS
    candidates = [(x * LEPTONS + LEPTONS // 2, y * LEPTONS + LEPTONS // 2)
                  for dy in range(-10, 11) for dx in range(-10, 11)
                  for x, y in [(bcx + dx, bcy + dy)]
                  if 0 <= x < md.width and 0 <= y < md.height]
    pq = pb_uint(1, e["pointer_self"]) + pb_uint(2, house["self"])
    for wx, wy in candidates[:PLACE_QUERY_MAX]:
        pq += pb_bytes(3, pb_uint(1, wx) + pb_uint(2, wy))
    rq = c.send_command(NS + "PlaceQuery", pq, poll_timeout=20000)
    legal = ([parse_coordinates(v) for _, v in fmap(rq["payload"]).get(3, [])]
             if not rq["code"] else [])

    recovered = None
    if legal:
        spot = legal[0]
        p2 = (pb_bytes(1, pb_uint(10, ptr))
              + pb_bytes(2, pb_uint(1, spot["x"]) + pb_uint(2, spot["y"])))
        rr = c.send_command(NS + "PlaceBuilding", p2, poll_timeout=15000)
        recovered = {"cell": [spot["x"] // LEPTONS, spot["y"] // LEPTONS],
                     "result_code": rr["code"], "error": rr["error"][:120]}

    res["23"] = {
        "status": "pass",
        "far_cell": [far[0] // LEPTONS, far[1] // LEPTONS],
        "illegal_result_code": r["code"],
        "illegal_error": r["error"][:200],
        "legal_recovery": recovered,
    }


def sellable(c, types):
    st = c.get_state()
    return [o for o in st.own_objects()
            if o["object_type"] == 6 and "Power Plant" in types.name(o)]


def test_06_sell(c, res, types):
    """变卖建筑：对象应消失且资金增加。"""
    targets = sellable(c, types)
    if not targets:
        res["6"] = {"status": "skip", "reason": "没有可卖的发电厂"}
        return
    t = targets[0]
    before = c.get_state().player_house()["money"]
    c.send_async(NS + "UnitOrder", order_payload([t["self"]], UA_SELL))
    s, polls = wait_until(c, lambda s: s.object(t["self"]) is None, max_polls=120)
    after = c.get_state()
    res["6"] = {
        "status": "pass" if s is not None else "fail",
        "object": t["self"],
        "cell": [t["coordinates"]["x"] // LEPTONS, t["coordinates"]["y"] // LEPTONS],
        "money_before": before,
        "money_after": after.player_house()["money"],
        "polls_used": polls,
    }


def test_07_sell_cell(c, res, types):
    """变卖所在格：不需要 object_addresses。"""
    targets = sellable(c, types)
    if not targets:
        res["7"] = {"status": "skip", "reason": "没有可卖的发电厂"}
        return
    t = targets[0]
    coords = (t["coordinates"]["x"], t["coordinates"]["y"])
    before = c.get_state().player_house()["money"]
    c.send_async(NS + "UnitOrder",
                 order_payload([], UA_SELL_CELL, coordinates=coords))
    s, polls = wait_until(c, lambda s: s.object(t["self"]) is None, max_polls=120)
    after = c.get_state()
    res["7"] = {
        "status": "pass" if s is not None else "fail",
        "cell": [coords[0] // LEPTONS, coords[1] // LEPTONS],
        "money_before": before,
        "money_after": after.player_house()["money"],
        "polls_used": polls,
    }


def test_11_attack(c, res, types):
    """攻击指定目标对象。"""
    st = c.get_state()
    house = st.player_house()
    enemy_houses = {h["self"] for h in st.houses
                    if h["self"] != house["self"] and h["faction"] != "Neutral"}
    targets = [o for o in st.objects
               if o["house"] in enemy_houses and o["object_type"] in (1, 15)
               and not o["in_limbo"]]
    if not targets:
        res["11"] = {"status": "skip", "reason": "找不到敌方单位"}
        return
    shooter = pick_idle_unit(st)
    if shooter is None:
        res["11"] = {"status": "skip", "reason": "没有 Guard 状态的己方载具"}
        return
    target = targets[0]
    c.send_async(NS + "UnitOrder",
                 order_payload([shooter["self"]], UA_ATTACK,
                               target_object=target["self"]))
    s, polls = wait_until(
        c, lambda s: (s.object(shooter["self"]) or {}).get("mission") == 1,
        max_polls=120)
    after = c.get_state().object(shooter["self"])
    res["11"] = {
        "status": "pass" if s is not None else "fail",
        "shooter": shooter["self"],
        "shooter_name": types.name(shooter),
        "target": target["self"],
        "target_name": types.name(target),
        "mission": after["mission"] if after else None,
        "mission_name": MISSION_NAMES.get(after["mission"]) if after else None,
        "polls_used": polls,
    }


def run_final(c):
    res = {}
    types = c.read_object_types()
    test_23_illegal_place(c, res, types)
    test_06_sell(c, res, types)
    test_07_sell_cell(c, res, types)
    test_11_attack(c, res, types)
    return res


# ------------------------------------------------------------------ AddEvent
EV_PRODUCE, EV_SUSPEND, EV_ABANDON = 0xE, 0xF, 0x10


def addevent_payload(event_type, rtti_id, heap_id, frame_delay=0):
    """AddEvent{event{event_type, production{rtti_id, heap_id}}, frame_delay}。"""
    prod = pb_uint(1, rtti_id) + pb_uint(2, heap_id)
    ev = pb_uint(4, event_type) + pb_bytes(10, prod)
    return pb_bytes(1, ev) + pb_uint(2, frame_delay)


def test_addevent(c, res, types):
    """用 AddEvent 注入生产队列事件，检验暂停与取消生产。

    `ProduceOrder` 忽略 action 字段，暂停与取消只能绕道 AddEvent。`add_event`
    会校验 `(rtti_id, heap_id)` 必须能在类型表中找到，故必须传真实值。
    """
    entry = {}
    e = find_type(types, "Power Plant")
    if e is None:
        res["addevent"] = {"status": "fail", "note": "找不到 Allied Power Plant"}
        return
    rtti_id, heap_id = e["type"], e["array_index"]
    entry["type"] = {"name": e["name"], "rtti_id": rtti_id, "heap_id": heap_id}

    r = c.send_command(NS + "ProduceOrder",
                       pb_bytes(1, object_type_payload(e)) + pb_uint(2, PRODUCE_BEGIN),
                       poll_timeout=10000)
    entry["produce"] = {"code": r["code"], "error": r["error"][:160]}
    if r["code"]:
        entry["status"] = "fail"
        res["addevent"] = entry
        return

    timer = None
    for _ in range(120):
        mine = own_factories(c.get_state())
        if mine and mine[0]["progress_timer"] > 3:
            timer = mine[0]["progress_timer"]
            break
        time.sleep(0.05)
    entry["timer_before_suspend"] = timer

    def snapshot():
        return [{"timer": f["progress_timer"], "on_hold": f["on_hold"],
                 "completed": f["completed"]} for f in own_factories(c.get_state())]

    r2 = c.send_command(NS + "AddEvent",
                        addevent_payload(EV_SUSPEND, rtti_id, heap_id), 10000)
    entry["suspend"] = {"code": r2["code"], "error": r2["error"][:160],
                        "result_type": r2["type"]}
    time.sleep(1.0)
    first = snapshot()
    time.sleep(1.2)
    second = snapshot()
    entry["after_suspend_1s"] = first
    entry["after_suspend_2s"] = second
    entry["suspend_stalled"] = (
        bool(first) and bool(second) and first[0]["timer"] == second[0]["timer"])

    r3 = c.send_command(NS + "AddEvent",
                        addevent_payload(EV_ABANDON, rtti_id, heap_id), 10000)
    entry["abandon"] = {"code": r3["code"], "error": r3["error"][:160],
                        "result_type": r3["type"]}
    time.sleep(1.0)
    entry["after_abandon"] = snapshot()

    entry["status"] = "pass"
    res["addevent"] = entry


def run_addevent(c):
    res = {}
    types = c.read_object_types()
    test_addevent(c, res, types)
    return res


RUNNERS = {"timing": run_timing, "batch": run_batch, "engage": run_engage,
           "observe": run_observe, "build": run_build, "final": run_final,
           "addevent": run_addevent}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("group", choices=sorted(RUNNERS))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=14521)
    ap.add_argument("--no-focus", action="store_true",
                    help="不占用焦点（调试用；失焦时排队命令不会执行）")
    args = ap.parse_args()

    c = Client(args.host, args.port)
    c.connect()
    try:
        if args.no_focus:
            res = RUNNERS[args.group](c)
        else:
            with batchkit.focused_batch(f"{args.group}"):
                res = RUNNERS[args.group](c)
    finally:
        c.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"survey-{args.group}.json"
    path.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n结果已写入 {path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
