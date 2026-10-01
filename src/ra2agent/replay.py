"""离线回放：拿一局录下来的帧，验证一条技法在这个局面里到底行不行。

「沉淀」缺的就是这一环。模型写完技法，得先在这类局面上证明它该出手时出手、发出的
命令能过前置校验，才谈得上注册进库。本模块给两样东西：

- **录制**：把真局的帧与地图存成一个 JSON 场景（帧是原始 protobuf 字节，逐字节保真）；
- **回放**：把场景喂给技法层，用真技法、真运行时、真前置校验跑若干拍，出一份判定。

回放里不连接游戏：命令由一个记账用的假执行器接住，但它**先过真的 `Executor.plan`**，
所以越界坐标、非己方对象、mission 非法这类在真机上会崩或必然失败的命令会被当场抓住。

用法：

```sh
# 录一段真局（需游戏在跑）
python3 -m ra2agent.replay --record --out scenario.json --frames 60 --interval 0.5
# 回放验证
python3 -m ra2agent.replay scenario.json --tactic advance_to_cell --units 213,214 \\
    --params cell=112,60 --ticks 8
```
"""
import argparse
import base64
import json
import sys
import time
from dataclasses import dataclass, field

from .engine.client import Client, CommandResult
from .runtime.executor import CommandPlan, ExecutionOutcome, Executor
from .engine.identity import IdentityTable
from .runtime.intents import Scope, TacticCall
from .runtime.micro import MicroLayer
from .engine.observation import Observer
from .engine.proto import pb_bytes
from .engine.state import GameState, MapData
from .tactics import TacticPolicy, TacticRegistry
from .engine.validate import Validator

#: 场景文件的格式版本。
SCENARIO_VERSION = 1
#: 回放默认跑多少拍。
DEFAULT_TICKS = 8
#: 已定技法必须过的期望。
DEFAULT_MIN_INTENTS = 1


@dataclass(frozen=True)
class Scenario:
    """一局录下来的东西：若干帧加一张地图。"""

    frames: tuple            # GameState 的原始字节
    map_soa: bytes | None = None
    note: str = ""
    created: float = field(default_factory=time.time)

    # ------------------------------------------------------------ 构造
    @classmethod
    def record(cls, client, frames=DEFAULT_TICKS, interval=0.5, note="") -> "Scenario":
        """从活着的游戏录：逐帧取状态，地图取一次。"""
        raw = []
        for _ in range(frames):
            raw.append(bytes(client.get_state().raw))
            time.sleep(interval)
        map_data = client.read_map()
        return cls(frames=tuple(raw), map_soa=bytes(map_data.raw), note=note)

    # ------------------------------------------------------------ 还原
    def states(self) -> tuple:
        """还原成 `GameState` 序列。"""
        return tuple(GameState.parse(frame) for frame in self.frames)

    def map_data(self) -> MapData | None:
        """还原地图；没录地图时返回 `None`。"""
        if not self.map_soa:
            return None
        # MapData.parse 吃的是 ReadValue 响应，故按原样套回两层
        return MapData.parse(pb_bytes(1, pb_bytes(5, self.map_soa)))

    # ------------------------------------------------------------ 序列化
    def to_dict(self) -> dict:
        """序列化为 JSON 可编码的字典。"""
        return {"version": SCENARIO_VERSION,
                "note": self.note,
                "created": self.created,
                "map_soa": base64.b64encode(self.map_soa).decode() if self.map_soa else "",
                "frames": [base64.b64encode(f).decode() for f in self.frames]}

    @classmethod
    def from_dict(cls, data) -> "Scenario":
        """从字典还原；版本不符就报错，不猜。"""
        version = data.get("version")
        if version != SCENARIO_VERSION:
            raise ValueError(f"场景格式版本不符：{version!r}，本程序认 {SCENARIO_VERSION}")
        return cls(frames=tuple(base64.b64decode(f) for f in data["frames"]),
                   map_soa=base64.b64decode(data["map_soa"]) if data.get("map_soa") else None,
                   note=data.get("note", ""), created=data.get("created", 0.0))

    def save(self, path) -> None:
        """写入文件。"""
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False)
            handle.write("\n")

    @classmethod
    def load(cls, path) -> "Scenario":
        """从文件读取。"""
        with open(path, encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))


@dataclass(frozen=True)
class Expectation:
    """对一次回放的期望。`settle=None` 表示不要求任务结算。"""

    min_intents: int = DEFAULT_MIN_INTENTS
    settle: str | None = None
    no_plan_errors: bool = True


@dataclass(frozen=True)
class ReplayReport:
    """一次回放的判定。"""

    tactic: str
    ticks: int
    intents: tuple = ()
    plan_errors: tuple = ()
    modes: tuple = ()
    settlement: dict | None = None
    failures: tuple = ()

    @property
    def ok(self) -> bool:
        """是否满足全部期望。"""
        return not self.failures

    def render(self) -> str:
        """渲染成模型读的文本，形状固定。"""
        lines = [f"回放 {self.tactic}｜{self.ticks} 拍｜产出 {len(self.intents)} 条意图"]
        for index, (tick, kinds) in enumerate(self.intents, 1):
            detail = "、".join(kinds) if kinds else "无"
            modes = "、".join(f"{name} {count}" for name, count in self.modes[index - 1])
            lines.append(f"- 拍 {tick}：{detail}｜{modes or '无单位'}")
        if self.plan_errors:
            lines.append(f"前置校验不通过 {len(self.plan_errors)} 条：")
            for error in self.plan_errors:
                lines.append(f"- {error}")
        else:
            lines.append("前置校验：全部通过")
        if self.settlement is not None:
            lines.append(f"结算：{self.settlement['state']}｜到位 "
                         f"{len(self.settlement['arrived'])} 损失 "
                         f"{len(self.settlement['lost'])} 失败 "
                         f"{len(self.settlement['failed'])}")
        else:
            lines.append("结算：未结束")
        lines.append("判定：" + ("通过" if self.ok else "不通过：" + "；".join(self.failures)))
        return "\n".join(lines)


class _TimelineClient:
    """按帧推进的假客户端：只回答状态，不发送任何命令。"""

    def __init__(self, states):
        self.states = list(states)
        self.index = 0
        self.reads = 0

    @property
    def current(self) -> GameState:
        """当前帧。"""
        return self.states[min(self.index, len(self.states) - 1)]

    def get_state(self):
        self.reads += 1
        return self.current

    def advance(self, steps=1) -> None:
        """时间线前进，不越过最后一帧。"""
        self.index = min(self.index + steps, len(self.states) - 1)


class _RecordingExecutor:
    """接住技法产出的意图：先过真的 `Executor.plan` 做前置校验，再记下来。"""

    def __init__(self, planner):
        self.planner = planner
        self.plans: list = []
        self.errors: list = []
        self.frames: int = 0

    def execute(self, intent, state) -> ExecutionOutcome:
        """校验并记账；校验不过就照原样抛，让运行时按真实规则处置。"""
        try:
            plan = self.planner.plan(intent, state)
        except Exception as error:
            self.errors.append(f"{intent.kind}：{type(error).__name__}: {error}")
            raise
        self.plans.append((intent, plan))
        self.frames += 1
        return ExecutionOutcome(
            intent_id=intent.id, kind=intent.kind, plan=plan, frames_waited=0,
            polls=1, state=state,
            result=CommandResult(type=plan.command, payload=b"", code=None, error=""),
            receipt="simulated", evidence="planning_only")

    def kinds(self) -> list:
        """本次拍产出的意图类型。"""
        return [intent.kind for intent, _ in self.plans]

    def reset(self) -> None:
        """清掉本拍的记录。"""
        self.plans = []


def replay(scenario: Scenario, tactic: str, units=(), params=None, *, ticks=DEFAULT_TICKS,
           expect=None, registry=None, map_data=None, log=None) -> ReplayReport:
    """把一条技法放进录下来的局面里跑，返回判定。

    命令由记账执行器接住（不连接游戏），但每条都先过 `Executor.plan`：前置校验不过
    的命令会被抓住，运行时按真实规则把它记成失败。
    """
    states = scenario.states()
    if not states:
        raise ValueError("场景里没有帧")
    map_data = map_data if map_data is not None else scenario.map_data()
    identity = IdentityTable()
    identity.update(states[0])
    client = _TimelineClient(states)
    observer = Observer(client, identity=identity, map_data=map_data)
    registry = registry or TacticRegistry(
        TacticPolicy.load("config/tactics.json")).load_builtin()
    planner = Executor(client, identity, types=None, validator=Validator(map_data))
    recorder = _RecordingExecutor(planner)
    layer = MicroLayer(observer, registry, recorder, log=log)

    call = TacticCall(tactic=tactic, params=dict(params or {}),
                      scope=Scope(objects=tuple(units)),
                      created_frame=states[0].frame)
    try:
        layer.assign(call, observer.poll())
    except Exception as error:
        # 连编队都建不起来（对象不存在、技法名不对）：直接给不通过的判定
        return ReplayReport(tactic=tactic, ticks=0,
                            failures=(f"{type(error).__name__}: {error}",))

    intents, modes = [], []
    for tick in range(1, ticks + 1):
        recorder.reset()
        layer.tick()
        intents.append((tick, tuple(recorder.kinds())))
        modes.append(tuple(sorted(
            (str(unit.mode), 1) for unit in (layer.squads()[0].units
                                             if layer.squads() else []))))
        if not layer.squads():
            break
        client.advance()

    expect = expect or Expectation()
    failures = []
    produced = sum(len(kinds) for _, kinds in intents)
    if produced < expect.min_intents:
        failures.append(f"只产出 {produced} 条意图，少于要求的 {expect.min_intents}")
    if expect.no_plan_errors and recorder.errors:
        failures.append(f"{len(recorder.errors)} 条命令没过前置校验")
    settlement = layer.completed[-1] if layer.completed else None
    if expect.settle is not None:
        got = settlement["state"] if settlement else "未结束"
        if got != expect.settle:
            failures.append(f"结算为 {got}，期望 {expect.settle}")
    return ReplayReport(tactic=tactic, ticks=ticks, intents=tuple(intents),
                        plan_errors=tuple(recorder.errors), modes=tuple(modes),
                        settlement=settlement, failures=tuple(failures))


def _parse_value(raw):
    """先按 JSON 解析；`1,2` 这种坐标写法退一步按逗号拆成数字元组。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    parts = [piece.strip() for piece in raw.split(",")]
    if len(parts) > 1:
        try:
            return tuple(float(piece) if "." in piece else int(piece)
                         for piece in parts)
        except ValueError:
            pass
    return raw


def _parse_params(pairs) -> dict:
    """把 `key=value` 解析成参数字典。"""
    out = {}
    for pair in pairs or ():
        if "=" not in pair:
            raise ValueError(f"参数要写成 key=value：{pair!r}")
        key, _, raw = pair.partition("=")
        out[key] = _parse_value(raw)
    return out


def main(argv=None) -> int:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="技法回放验证")
    parser.add_argument("scenario", nargs="?", help="场景文件")
    parser.add_argument("--record", action="store_true", help="录制模式：连游戏录一段")
    parser.add_argument("--out", help="录制输出路径")
    parser.add_argument("--frames", type=int, default=60, help="录多少帧")
    parser.add_argument("--interval", type=float, default=0.5, help="录制间隔秒")
    parser.add_argument("--note", default="", help="场景备注")
    parser.add_argument("--tactic", help="要验证的技法名")
    parser.add_argument("--units", default="", help="对象 id，逗号分隔")
    parser.add_argument("--params", action="append", help="技法参数 key=value，可重复")
    parser.add_argument("--ticks", type=int, default=DEFAULT_TICKS)
    parser.add_argument("--expect-settle", default=None,
                        help="期望的结算状态：satisfied / failed / expired / superseded")
    args = parser.parse_args(argv)

    if args.record:
        if not args.out:
            parser.error("录制要给 --out")
        client = Client()
        client.connect()
        try:
            scenario = Scenario.record(client, args.frames, args.interval, args.note)
        finally:
            client.close()
        scenario.save(args.out)
        print(f"已录制 {len(scenario.frames)} 帧到 {args.out}")
        return 0

    if not args.scenario or not args.tactic:
        parser.error("回放要给场景文件与 --tactic")
    scenario = Scenario.load(args.scenario)
    units = tuple(int(u) for u in args.units.split(",") if u.strip())
    expectation = Expectation(settle=args.expect_settle)
    report = replay(scenario, args.tactic, units, _parse_params(args.params),
                    ticks=args.ticks, expect=expectation)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
