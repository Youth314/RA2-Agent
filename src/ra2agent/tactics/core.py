"""技法库的框架：元数据、注册表、等级门控与调用链。

设计见 `.agents/notes/技法框架.md`。要点：

- 技法是普通 Python 函数：读局面，返回意图。只读、不做 I/O、不碰引擎。
- 内层调用必须经 `TacticContext.call`，门控、适用条件、深度与环检测、调用链
  日志都在那里生效，直接 import 别的技法会绕过全部保险。
- 两道闸：上下文闸（不进卡片）与执行闸（调用时报错）。只藏起来不够，模型可能
  凭记忆硬调一个名字。
"""
import hashlib
import inspect
import json
import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable

from ..constants import WAIT_GRACE_FRAMES
from ..errors import TacticDenied, TacticError, TacticFailed
from ..runtime.intents import Intent, Layer, Scope
from .conditions import NEEDS_PARAMS, check_conditions, explain


class Level(StrEnum):
    """技法等级。判据是对称性：人类在同一版本、不开挂能做到的算技法。"""

    NORMAL = "normal"      # 正常玩法
    EDGE = "edge"          # 时序与边界技巧，人也能做
    EXPLOIT = "exploit"    # 明确 bug，人难复现
    CHEAT = "cheat"        # 只有 Agent 做得到：读全图、伪造事件、直接加钱


#: 等级由低到高，用于比较门槛。
LEVEL_ORDER = {Level.NORMAL: 0, Level.EDGE: 1, Level.EXPLOIT: 2, Level.CHEAT: 3}


class Mode(StrEnum):
    """调用方的模式，决定卡片里能看到什么。"""

    MATCH = "match"        # 对战：只看顶层卡片
    OFFLINE = "offline"    # 离线：卡片加零件，用于写与改技法


#: `Param.default` 取该值时表示必填。
REQUIRED = object()


@dataclass(frozen=True)
class Param:
    """一个参数：名字、默认值、说明，以及取值检查。

    `check` 在受理时就把不合法的值挡回去。只查「在不在」不够：模型可能给出
    `cell: null` 这类形状不对的值，一路走到技法里才炸，那时它拿到的是一句
    看不懂的 TypeError。
    """

    name: str
    default: object = REQUIRED
    help: str = ""
    check: Callable[[object], bool] | None = None

    @property
    def required(self) -> bool:
        """是否必填。"""
        return self.default is REQUIRED


def is_cell(value) -> bool:
    """是否是 `(x, y)` 两个整数。JSON 往返后会变成列表，故两者都收。"""
    return (isinstance(value, (tuple, list)) and len(value) == 2
            and all(isinstance(v, int) and not isinstance(v, bool) for v in value))


def is_stance(value) -> bool:
    """是否是已知姿态。"""
    from ..runtime.intents import Stance
    return value in tuple(Stance)


def is_optional_cell(value) -> bool:
    """可省略的格参数：`None` 或 `(x, y)`。

    `Param` 的默认值也会过一遍检查，故「不填就用技法的兜底逻辑」这类参数不能挂
    `is_cell`——`None` 会被判非法。
    """
    return value is None or is_cell(value)


def is_non_empty_str(value) -> bool:
    """非空字符串。类型名一类的参数用它，别让空白串一路走到类型表里。"""
    return isinstance(value, str) and bool(value.strip())


def is_non_negative_int(value) -> bool:
    """是否是非负整数。"""
    return (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def is_positive_int(value) -> bool:
    """是否是正整数。用于「数量」「半径」这类参数：0 没有意义。"""
    return (isinstance(value, int) and not isinstance(value, bool) and value > 0)


def is_bool(value) -> bool:
    """是否是布尔。用于「要不要去追」这类开关参数。"""
    return isinstance(value, bool)


def is_positive_number(value) -> bool:
    """是否是正数。"""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value > 0)


@dataclass(frozen=True)
class Trigger:
    """技法何时**自己**跑起来。默认只在模型 `call` 时跑。

    自动触发产出的是**脉冲**：跑一次、下发一次、不建编队。三处理由：

    - 房子级动作（造电厂一类）不需要单位，而任务模型是「一队单位 + 意图」；
    - 给 `Produce` 绑一队单位会让它每拍重发，重复下单；
    - 脉冲不会长期占着单位的租约，模型随时还能自己指挥它们。

    要持续控制单位的技法（推进、缠斗）仍由模型显式 `call`。
    """

    #: 命中任一事件就跑。取值见 `events.EventKind`。
    events: tuple = ()
    #: 每这么多游戏帧跑一次。按帧不按秒——失焦时帧不走，恰好符合「游戏时间」。
    every_frames: int = 0
    #: 是否仍允许模型显式调用。
    on_call: bool = True

    @classmethod
    def on(cls, *kinds) -> "Trigger":
        """命中这些事件时跑。"""
        return cls(events=tuple(kinds))

    @classmethod
    def every(cls, frames) -> "Trigger":
        """每 `frames` 个游戏帧跑一次。"""
        return cls(every_frames=frames)

    @classmethod
    def automatic(cls, *kinds, every_frames=0, on_call=False) -> "Trigger":
        """既要事件、又要定时；由写技法的人显式声明。"""
        return cls(events=tuple(kinds), every_frames=every_frames, on_call=on_call)

    @property
    def automatic_triggered(self) -> bool:
        """会不会自己跑起来。"""
        return bool(self.events or self.every_frames)

    def text(self) -> str:
        """名片里怎么显示。"""
        parts = []
        if self.events:
            parts.append("事件 " + "、".join(str(k) for k in self.events))
        if self.every_frames:
            parts.append(f"每 {self.every_frames} 帧")
        if not parts:
            return "只由模型调用"
        if self.on_call:
            parts.append("也可显式调用")
        return "；".join(parts)


@dataclass(frozen=True)
class TacticInfo:
    """一张技法的名片。模型只看它，不看代码。"""

    name: str
    summary: str
    layer: Layer = Layer.L1_TACTIC
    params: tuple = ()
    requires: tuple = ()            # 适用条件标签，见 conditions.py
    level: Level = Level.NORMAL
    expose: bool = True             # 是否进对战时的卡片
    source: str = "builtin"         # builtin / model / human
    version: int = 1
    trigger: Trigger = field(default_factory=Trigger)   # 何时自己跑
    #: 这一拍产不出意图时，任务**当场收工**还是继续等下一拍。
    #:
    #: 两种情况代码上一样（`run` 返回空元组），语义却不同：`deploy_mcv` 对一台已
    #: 展开的建造厂是「没事可做」，该把单位交还；`guard_area` 没目标时是「等下一
    #: 拍」，收工就改掉了它的语义。默认继续等（保守），一次性技法自己标 True。
    idle_ends_task: bool = False
    #: 继续等的时候最多等多少帧，等满收工交还单位。`None` 表示不设上限。
    #:
    #: 默认取自 `constants.WAIT_GRACE_FRAMES`（约两栋楼的建造周期）。自带生命周期
    #: 的技法（`guard_area` 有 `max_frames`）可以豁免，自己负责收尾。
    wait_grace_frames: int | None = WAIT_GRACE_FRAMES


@dataclass(frozen=True)
class Tactic:
    """技法：名片加函数。"""

    info: TacticInfo
    run: Callable[["TacticContext"], tuple]


@dataclass(frozen=True)
class Card:
    """给模型看的一行。只有名字、一句话、参数与条件，没有代码。"""

    name: str
    summary: str
    level: str
    params: tuple = ()
    requires: tuple = ()
    trigger: str = ""

    def text(self) -> str:
        """卡片文本。"""
        parts = [f"{self.name}（{self.level}）：{self.summary}"]
        if self.params:
            shown = "，".join(
                f"{p.name}={p.default if not p.required else '必填'}" for p in self.params)
            parts.append(f"参数：{shown}")
        if self.requires:
            parts.append("条件：" + "，".join(self.requires))
        if self.trigger and self.trigger != "只由模型调用":
            parts.append("自动：" + self.trigger)
        return " ｜ ".join(parts)


class _Budget:
    """一次顶层调用共享的额度，防止技法死循环地互相调用。"""

    def __init__(self, max_calls):
        self.max_calls = max_calls
        self.calls = 0

    def spend(self):
        """消耗一次调用额度。"""
        self.calls += 1
        if self.calls > self.max_calls:
            raise TacticError(f"一次顶层调用的技法次数超过 {self.max_calls}")


class TacticContext:
    """一次技法调用拿到的全部东西。

    技法只读：不改传入的任何东西，只返回意图。需要跨帧记忆时写 `memo`，它按
    「技法名 + 对象」隔离，任务结束清空。
    """

    def __init__(self, *, registry, tactic, observation, subject, params, frame,
                 memo, log, chain, attempt, budget, events=()):
        self._registry = registry
        self.tactic = tactic
        self.observation = observation
        self.subject = subject
        self.params = params
        self.frame = frame
        self.memo = memo
        self.log = log
        self.chain = chain
        self.attempt = attempt
        self._budget = budget
        #: 这一拍新发生的事件（自动触发时由触发层带下来）。**编队任务里为空**：
        #: 事件只喂给「按事件触发的脉冲」，否则同一件事会被每条在管任务各报一次。
        self.events = tuple(events or ())

    @property
    def name(self) -> str:
        """当前技法的名字。"""
        return self.tactic.info.name

    @property
    def types(self):
        """对象类型表。没取到类型表时为 `None`。"""
        return getattr(self.observation, "types", None)

    def type_pointer(self, name, rtti=None):
        """按注册名（`MTNK`）或显示名（`Grizzly Battle Tank`）解析类型指针。

        `Produce` 一类意图要的是指针，故这里给个直接的入口。找不到返回 `None`——
        技法应当据此放弃，而不是拿个假指针去下单。

        注册名要有人往类型表里填过别名才认得出；引擎自己只给显示名。
        """
        table = self.types
        if table is None:
            return None
        found = table.resolve(name, rtti)
        return found.pointer if found is not None else None

    def call(self, name, *, optional=False, **params) -> tuple:
        """调用另一条技法并把它的意图原样带回。

        `optional=True` 只放行「适用条件不满足」（返回空元组），**不放行等级与
        启用门槛**：被禁用的技法不能靠包一层壳调用。
        """
        return self._registry.invoke(name, self, params, optional=optional)

    def intent(self, cls, *, scope=None, **payload) -> Intent:
        """按信封约定造一条给基础设施的意图：层、帧号、涉及对象都自动填好。

        没给 `scope` 就用本队单位。一个都没有时用 `Scope.empty()` 而不是报错——
        阵营级动作（造东西一类）本来就不涉及对象，自动触发的脉冲尤其如此。
        """
        units = tuple(scope) if scope is not None else self.subject.agents()
        ownership = Scope(objects=units) if units else Scope.empty()
        return cls(layer=Layer.L1_TACTIC, created_frame=self.frame,
                   scope=ownership, **payload)

    def remember(self, key, value) -> None:
        """往记事本里写一条，键自动带上技法名。"""
        self.memo[(self.name, key)] = value

    def recall(self, key, default=None):
        """从记事本里读一条。"""
        return self.memo.get((self.name, key), default)

    def __repr__(self):
        return f"TacticContext({self.name}, chain={list(self.chain)})"


@dataclass
class TacticPolicy:
    """谁能用、用到什么程度。可存成 JSON，改配置不必改代码。"""

    max_level: dict = field(default_factory=lambda: {Layer.L1_TACTIC: Level.NORMAL})
    enabled: frozenset = frozenset()      # 空集表示不额外限制
    disabled: frozenset = frozenset()
    max_depth: int = 8
    max_calls: int = 32
    max_intents: int = 32
    timeout_ms: int = 50

    def allows(self, info: TacticInfo) -> bool:
        """这条技法按当前策略能否调用。"""
        if info.name in self.disabled:
            return False
        if self.enabled and info.name not in self.enabled:
            return False
        limit = self.max_level.get(info.layer, Level.NORMAL)
        return LEVEL_ORDER[info.level] <= LEVEL_ORDER[limit]

    def to_dict(self) -> dict:
        """序列化为 JSON 可编码的字典。"""
        return {
            "max_level": {str(int(layer)): str(level)
                          for layer, level in self.max_level.items()},
            "enabled": sorted(self.enabled),
            "disabled": sorted(self.disabled),
            "max_depth": self.max_depth,
            "max_calls": self.max_calls,
            "max_intents": self.max_intents,
            "timeout_ms": self.timeout_ms,
        }

    @classmethod
    def from_dict(cls, data) -> "TacticPolicy":
        """从字典还原。缺项用默认值补齐。"""
        known = {f.name for f in cls.__dataclass_fields__.values()}
        extra = set(data) - known
        if extra:
            raise TacticError(f"策略里有不认识的字段：{sorted(extra)}")
        fields = dict(data)
        if "max_level" in fields:
            fields["max_level"] = {Layer(int(layer)): Level(level)
                                   for layer, level in fields["max_level"].items()}
        for key in ("enabled", "disabled"):
            if key in fields:
                fields[key] = frozenset(fields[key])
        return cls(**fields)

    @classmethod
    def load(cls, path) -> "TacticPolicy":
        """从 JSON 文件读取；文件不存在时用默认策略。格式错误则报错。"""
        if not os.path.exists(path):
            return cls()
        with open(path, encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def save(self, path) -> None:
        """写入 JSON 文件。"""
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2,
                      sort_keys=True)
            handle.write("\n")


class TacticRegistry:
    """技法的存放与调用。所有调用都从这里过，保险才有效。"""

    def __init__(self, policy=None, log=None):
        self.policy = policy or TacticPolicy()
        self.log = log
        self._tactics: dict = {}

    # ------------------------------------------------------------ 注册
    def register(self, tactic: Tactic) -> Tactic:
        """登记一条技法。重名报错。"""
        name = tactic.info.name
        if name in self._tactics:
            raise TacticError(f"技法名重复：{name}")
        if not name or not tactic.info.summary:
            raise TacticError("技法必须有名字与一句话说明")
        trigger = tactic.info.trigger
        if trigger.every_frames < 0:
            raise TacticError(f"技法 {name} 的触发间隔为负：{trigger.every_frames}")
        if not trigger.automatic_triggered and not trigger.on_call:
            raise TacticError(f"技法 {name} 既不能自动触发、也不许显式调用，永远跑不到")
        if trigger.automatic_triggered:
            # 自动触发时模型不在场，没人填必填参数
            needed = [p.name for p in tactic.info.params if p.default is REQUIRED]
            if needed:
                raise TacticError(
                    f"技法 {name} 会自己跑，但有必填参数 {needed}——自动触发时没人填，"
                    f"请给默认值或改成只由模型调用")
        self._tactics[name] = tactic
        return tactic

    def load(self, tactics) -> "TacticRegistry":
        """批量登记，返回自身以便连写。"""
        for tactic in tactics:
            self.register(tactic)
        return self

    def load_builtin(self) -> "TacticRegistry":
        """登记内置技法，返回自身以便连写。"""
        from . import builtin
        return self.load(builtin.TACTICS)

    def get(self, name) -> Tactic:
        """按名字取技法；不存在则报错。"""
        found = self._tactics.get(name)
        if found is None:
            raise TacticError(f"没有这条技法：{name}")
        return found

    def names(self) -> tuple:
        """全部技法名。"""
        return tuple(sorted(self._tactics))

    def __len__(self):
        return len(self._tactics)

    # ------------------------------------------------------------ 可见面
    def cards(self, mode=Mode.MATCH, observation=None, subject=None) -> list:
        """当前该给模型看的卡片。

        对战模式只给 `expose` 且被策略放行的；给了局面与对象时，再按适用条件
        筛掉此刻用不上的。离线模式全给，包括零件与被停用的。
        """
        out = []
        for name in self.names():
            tactic = self._tactics[name]
            info = tactic.info
            if mode == Mode.MATCH:
                if not info.expose or not self.policy.allows(info):
                    continue
                if observation is not None and subject is not None:
                    if self.missing_conditions(info, observation, subject):
                        continue
            out.append(Card(name=info.name, summary=info.summary,
                            level=str(info.level), params=info.params,
                            requires=info.requires, trigger=info.trigger.text()))
        return out

    def catalog(self) -> str:
        """人类可读的清单，用于审阅与裁剪技法库。"""
        lines = [f"技法 {len(self._tactics)} 条｜策略："
                 f"{'、'.join(f'{k.label}<={v}' for k, v in self.policy.max_level.items())}"]
        for name in self.names():
            info = self._tactics[name].info
            marks = [str(info.level)]
            if not info.expose:
                marks.append("零件")
            if not self.policy.allows(info):
                marks.append("已停用")
            marks.append(info.source)
            lines.append(f"- {name}（{'，'.join(marks)}）：{info.summary}")
        return "\n".join(lines)

    def fingerprint(self) -> str:
        """技法库指纹，写入决策日志，使复盘可重现当时的能力集合。"""
        digest = hashlib.sha256()
        for name in self.names():
            tactic = self._tactics[name]
            digest.update(f"{name}@{tactic.info.version}|".encode())
            source = inspect.getsourcefile(tactic.run)
            if source and os.path.exists(source):
                with open(source, "rb") as handle:
                    digest.update(handle.read())
        return digest.hexdigest()[:16]

    # ------------------------------------------------------------ 调用
    def run(self, name, *, observation, subject, params=None, frame=0, memo=None,
            log=None, attempt=0, events=()) -> tuple:
        """顶层调用：校验参数、建上下文、调用、检查产出总量。"""
        tactic = self.get(name)
        clean = self.check_params(name, params or {})
        context = TacticContext(
            registry=self, tactic=tactic, observation=observation, subject=subject,
            params=clean, frame=frame, memo=memo if memo is not None else {},
            log=log or self.log, chain=(name,), attempt=attempt,
            budget=_Budget(self.policy.max_calls), events=events)
        intents = self._invoke(context)
        if len(intents) > self.policy.max_intents:
            raise TacticError(
                f"技法 {name} 产出 {len(intents)} 条意图，超过 "
                f"{self.policy.max_intents} 条上限")
        return intents

    def invoke(self, name, parent, params, optional=False) -> tuple:
        """内部调用：由 `TacticContext.call` 使用。"""
        tactic = self.get(name)
        if name in parent.chain:
            raise TacticError(f"技法调用出现环：{' → '.join(parent.chain + (name,))}")
        if len(parent.chain) >= self.policy.max_depth:
            raise TacticError(f"技法调用深度超过 {self.policy.max_depth}")
        parent._budget.spend()
        clean = self.check_params(name, params)
        context = TacticContext(
            registry=self, tactic=tactic, observation=parent.observation,
            subject=parent.subject, params=clean, frame=parent.frame,
            memo=parent.memo, log=parent.log, chain=parent.chain + (name,),
            attempt=parent.attempt, budget=parent._budget)
        try:
            return self._invoke(context)
        except TacticDenied as error:
            if optional and error.kind == "condition":
                self._record(context, "tactic_skipped", str(error))
                return ()
            raise

    # ------------------------------------------------------------ 内部
    def _invoke(self, context) -> tuple:
        """过两道闸，调用技法本体，异常隔离。"""
        info = context.tactic.info
        if not self.policy.allows(info):
            self._record(context, "tactic_denied", "被策略拒绝")
            raise TacticDenied(f"技法 {info.name}（{info.level}）被策略拒绝")
        missing = self.missing_conditions(info, context.observation, context.subject,
                                          context.params)
        if missing:
            self._record(context, "tactic_denied", f"适用条件不满足：{missing}")
            raise TacticDenied(
                f"技法 {info.name} 的适用条件不满足：{'、'.join(missing)}",
                kind="condition")
        try:
            intents = tuple(context.tactic.run(context))
        except TacticError:
            self._record(context, "tactic_failed", "技法自身报错")
            raise
        except Exception as error:            # 异常隔离：一次调用作废，运行时继续
            self._record(context, "tactic_failed", repr(error))
            raise TacticFailed(f"技法 {info.name} 抛异常：{error!r}") from error
        self._record(context, "tactic_run", f"产出 {len(intents)} 条意图")
        return intents

    def admit(self, name, observation, subject, params=None) -> str:
        """受理前的公共门槛：等级、适用条件。通过返回空串，否则返回原因。

        **这条闸只给自动触发用**（全仓库只有 `Autopilot._pulse` 调它）。等级门槛、
        停用名单、适用条件一项不少——触发层不是后门。

        **不看 `expose`**：`expose` 是「给不给模型看卡片」的概念，模型调用在
        `Command._accept` 里单独判。放在这里会出真事：自动层按 `trigger` 选定一条
        非暴露的技法（`automatic()` 本来就不看 expose），随后被这道闸拒掉、连
        `run` 都不调——`report_trouble` 就这么哑了整条唤醒链（触发命中 → 静默跳过，
        实机表现是「出了事没人叫模型」）。
        """
        try:
            info = self.get(name).info
        except TacticError as error:
            return str(error)
        if not self.policy.allows(info):
            return f"等级 {info.level} 超出门槛，或已被停用"
        missing = self.missing_conditions(info, observation, subject, params)
        if missing:
            return f"此刻用不上：{explain(missing)}"
        return ""

    def automatic(self) -> tuple:
        """会自己跑起来的技法。"""
        return tuple(self._tactics[name] for name in sorted(self._tactics)
                     if self._tactics[name].info.trigger.automatic_triggered)

    def missing_conditions(self, info, observation, subject, params=None) -> tuple:
        """返回此刻不满足的适用条件名。

        **参数要传进来**：`can_afford`、`cell_explored` 这类条件读 `context.params`，
        探针不给参数时它们必然为假，挂进 `requires` 等于把技法藏起来。

        `params=None` 表示**没有参数可给**（卡片筛选就是这种），此时读参数的条件
        一律**跳过**：它们判不出真假，判否只会让 `build_structure`、`train_unit`
        这类技法在卡片上消失，模型只能读源码才知道有它们。给了 `params`（哪怕是
        空字典，表示「这次调用就是这么调的」）就全部照判。

        `params` 可能是**未经 `check_params` 的原始请求**（受理点为了不改变拒因次序
        而先判条件），故条件要自己容忍缺项与缺默认值。
        """
        if not info.requires:
            return ()
        names = info.requires
        if params is None:
            names = tuple(name for name in names if name not in NEEDS_PARAMS)
            if not names:
                return ()
        probe = TacticContext(
            registry=self, tactic=Tactic(info=info, run=lambda context: ()),
            observation=observation, subject=subject, params=dict(params or {}),
            frame=0, memo={}, log=None, chain=(info.name,), attempt=0,
            budget=_Budget(0))
        return check_conditions(names, probe)

    def check_params(self, name, params) -> dict:
        """按声明的参数表校验并补默认值。

        指挥层在受理模型请求时先调它，使模型当场拿到「参数不对」而不是等一拍之后
        静默失败。
        """
        tactic = self.get(name)
        declared = {p.name: p for p in tactic.info.params}
        unknown = set(params) - set(declared)
        if unknown:
            raise TacticError(
                f"技法 {tactic.info.name} 不认识参数：{sorted(unknown)}")
        clean = {name: p.default for name, p in declared.items() if not p.required}
        clean.update(params)
        missing = [name for name, p in declared.items()
                   if p.required and name not in params]
        if missing:
            raise TacticError(f"技法 {tactic.info.name} 缺少参数：{missing}")
        for name, declared_param in declared.items():
            if declared_param.check is None or name not in clean:
                continue
            if not declared_param.check(clean[name]):
                raise TacticError(
                    f"技法 {tactic.info.name} 的参数 {name} 取值不合法："
                    f"{clean[name]!r}（{declared_param.help}）")
        return clean

    def _record(self, context, event, detail) -> None:
        """写调用链日志。"""
        if context.log is None:
            return
        context.log.record(context.frame, event, intent=None, detail={
            "tactic": context.name, "chain": list(context.chain),
            "params": dict(context.params), "note": detail})
