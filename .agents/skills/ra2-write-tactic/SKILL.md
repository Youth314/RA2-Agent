---
name: ra2-write-tactic
description: 写或改《红色警戒2》Agent 的技法（tactic）时使用。规定允许的 import、上下文 API、意图构造、名片字段、等级申报与离线验证流程。
---

# 写技法

技法（tactic）是 L0 之上唯一的能力形式：一个普通 Python 函数加一张名片。**对战
时不写技法**，只在离线写、验证、注册。库的形态与门控见
[.agents/notes/技法框架.md](../../notes/技法框架.md)。

## 一、技法是什么

```python
def run(ctx) -> tuple[Intent, ...]:
    """读局面，返回意图。"""
```

三条硬规矩：

1. **只读**：不改 `ctx` 里的任何东西，也不改模块级变量。要跨帧记东西用 `ctx.memo`。
2. **不做 I/O**：不读文件、不发网络、不起进程、不睡。它是纯函数。
3. **不碰引擎**：只返回意图，绝不自己发命令。下发统一由运行时过 `Validator` 与
   `Executor`。

## 二、允许的 import

白名单：`math`、`typing`、`dataclasses`、`enum`，以及本项目的
`ra2agent.intents`、`ra2agent.formation`、`ra2agent.constants`、`ra2agent.state`。

禁止：`os`、`sys`、`socket`、`subprocess`、`importlib`、`time`、`random`、
`open`、`eval`、`exec`。要随机或计时就说明用法错了——技法必须是确定性的。

## 三、上下文 API

| 成员 | 是什么 |
|---|---|
| `ctx.observation` | 一帧经迷雾过滤的观测；`map_data`、`visible_enemies`、`state` 都在这 |
| `ctx.subject` | 本层管的编队（只读）：`agents()` 本次该管的单位、`object_of(id)`、`agent_id(pointer)`、`cell_of(id)` |
| `ctx.params` | 本次调用的参数，已按名片补好默认值 |
| `ctx.frame` | 当前游戏帧 |
| `ctx.attempt` | 第几次尝试；卡住重来时由运行时递增，用来换落点 |
| `ctx.memo` | 跨帧记事本，按「技法名 + 键」隔离，任务结束清空 |
| `ctx.call(name, **params, optional=False)` | 调另一条技法 |
| `ctx.intent(cls, **payload)` | 按信封约定造意图 |
| `ctx.remember(key, value)` / `ctx.recall(key, default)` | 记事本的读写糖 |

## 四、能返回的意图

| 类 | 载荷 | 说明 |
|---|---|---|
| `MoveTo` | `units`、`cell`、`stance` | 移动；`stance` 取 `aggressive` / `passive` / `hold` |
| `Hold` | `units` | 停止并驻守 |
| `Attack` | `units`、`target` | 攻击指定对象 |
| `Produce` | `type_pointer` | 开始生产 |
| `Place` | `building`、`cell` | 放置已完工建筑 |
| `Sell` | `buildings` | 变卖建筑 |

**对象一律用 Agent 侧 id**，不是引擎指针——指针在单位变身时会变。引擎指针转 id
用 `ctx.subject.agent_id(pointer)`。

意图必须用 `ctx.intent` 造，它会自动填 `layer`、`created_frame` 与 `scope`：

```python
return (ctx.intent(MoveTo, units=ctx.subject.agents(), cell=(40, 40)),)
```

## 五、名片

```python
Tactic(TacticInfo(
    name="advance_to_cell",              # 唯一名，模型按它引用
    summary="把这队单位推进到目标格附近",   # 一句话，进卡片
    params=(Param("cell", REQUIRED, "目标格 (x, y)"),
            Param("stance", "aggressive", "姿态")),
    requires=("has_units", "has_map"),   # 适用条件
    level=Level.NORMAL,                  # 等级，见下
    expose=True,                         # 是否进对战时的卡片
    version=1), run)
```

条件名目前有 `has_units`、`has_map`、`has_enemies`、`no_enemies`、`cell_explored`。
不够用时去 `tactics/conditions.py` 加，不要在技法里偷偷判断。

## 六、等级怎么申报

判据是**对称性**：人类玩家在同一版本、不开挂的情况下做得到的，算技法。

| 等级 | 含义 | 默认 |
|---|---|---|
| `normal` | 正常玩法 | 开 |
| `edge` | 时序与边界技巧，人也能做 | 关，需显式开 |
| `exploit` | 明确 bug，人难复现 | 关，单独开关 |
| `cheat` | 只有 Agent 做得到：读全图、伪造事件、直接加钱 | 禁，只在调试模式 |

拿不准就报 `edge`，并在 `summary` 里写清依据。**没实测过的机制不要写成技法**，先
测绘。

## 七、组合

```python
def run(ctx):
    contact = ctx.call("engage_nearest", optional=True, radius=ctx.params["radius"])
    if contact:
        return contact
    return ctx.call("advance_to_cell", cell=ctx.params["cell"])
```

- 内层调用**必须**经 `ctx.call`，直接 import 别的技法会绕过门控与日志。
- `optional=True` 只在适用条件不满足时返回空元组，**不放行等级门槛**。
- 有效等级取整条链的最大值：`normal` 的外壳调 `exploit` 的内层，整条链按 `exploit` 算。
- 调用链不能有环；深度上限 8；一次顶层调用最多 32 次技法调用、32 条意图。

## 八、写完怎么验

**先单元测试，再谈上线。** 模板：

```python
def test_xxx(self):
    registry = TacticRegistry()
    registry.register(Tactic(TacticInfo(name="mine", summary="..."), run))
    intents = registry.run("mine", observation=make_observation(),
                           subject=FakeSubject(agents=(1, 2)),
                           params={"cell": (5, 5)}, frame=100)
    self.assertEqual([i.kind for i in intents], ["move_to", "move_to"])
```

必须覆盖：正常路径、条件不满足（应被拒）、缺参数（应报错）、边界（空单位、无地图）。

跑全套：`PYTHONPATH=src python3 -m unittest discover -s tests -t .`。

## 九、注册

新技法先放 `src/ra2agent/tactics/local/`（不入库），验证通过后再并入
`tactics/builtin/`。等级、条件或参数有任何一处说不清，就退回草稿。

## 十、禁止清单

- 直接发命令、直接调 `Client`、直接改 `GameState`。
- 读写文件、网络、进程、时钟、随机数。
- 捕获异常后当作没发生（要就让它抛，运行时负责隔离与记录）。
- 一次产出几十条命令（意图上限 32，超了直接拒绝）。
- 把「什么时候该用」藏进代码却不写 `requires`。
