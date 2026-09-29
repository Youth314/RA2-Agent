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

from ..errors import TacticDenied, TacticError, TacticFailed
from ..intents import Intent, Layer, Scope
from .conditions import check_conditions


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
    from ..intents import Stance
    return value in tuple(Stance)


def is_non_negative_int(value) -> bool:
    """是否是非负整数。"""
    return (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def is_positive_number(value) -> bool:
    """是否是正数。"""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value > 0)


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

    def text(self) -> str:
        """卡片文本。"""
        parts = [f"{self.name}（{self.level}）：{self.summary}"]
        if self.params:
            shown = "，".join(
                f"{p.name}={p.default if not p.required else '必填'}" for p in self.params)
            parts.append(f"参数：{shown}")
        if self.requires:
            parts.append("条件：" + "，".join(self.requires))
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
                 memo, log, chain, attempt, budget):
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

    @property
    def name(self) -> str:
        """当前技法的名字。"""
        return self.tactic.info.name

    def call(self, name, *, optional=False, **params) -> tuple:
        """调用另一条技法并把它的意图原样带回。

        `optional=True` 只放行「适用条件不满足」（返回空元组），**不放行等级与
        启用门槛**：被禁用的技法不能靠包一层壳调用。
        """
        return self._registry.invoke(name, self, params, optional=optional)

    def intent(self, cls, *, scope=None, **payload) -> Intent:
        """按信封约定造一条给基础设施的意图：层、帧号、涉及对象都自动填好。"""
        units = tuple(scope) if scope is not None else self.subject.agents()
        return cls(layer=Layer.L1_TACTIC, created_frame=self.frame,
                   scope=Scope(objects=units), **payload)

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
                            requires=info.requires))
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
            log=None, attempt=0) -> tuple:
        """顶层调用：校验参数、建上下文、调用、检查产出总量。"""
        tactic = self.get(name)
        clean = self.check_params(name, params or {})
        context = TacticContext(
            registry=self, tactic=tactic, observation=observation, subject=subject,
            params=clean, frame=frame, memo=memo if memo is not None else {},
            log=log or self.log, chain=(name,), attempt=attempt,
            budget=_Budget(self.policy.max_calls))
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
        missing = self.missing_conditions(info, context.observation, context.subject)
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

    def missing_conditions(self, info, observation, subject) -> tuple:
        """返回此刻不满足的适用条件名。"""
        if not info.requires:
            return ()
        probe = TacticContext(
            registry=self, tactic=Tactic(info=info, run=lambda context: ()),
            observation=observation, subject=subject, params={}, frame=0, memo={},
            log=None, chain=(info.name,), attempt=0, budget=_Budget(0))
        return check_conditions(info.requires, probe)

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
