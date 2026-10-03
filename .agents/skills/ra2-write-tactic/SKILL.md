---
name: ra2-write-tactic
description: 写或改《红色警戒2》Agent 的技法（tactic）时使用。规定允许的 import、上下文 API、意图构造、名片字段、等级申报与离线验证流程。
---

# 写技法

技法（tactic）是 L0 之上唯一的能力形式：一个普通 Python 函数加一张名片。**对战
时不写技法**，只在离线写、验证、注册。库的形态与门控见
[.agents/notes/设计/技法框架.md](../../notes/设计/技法框架.md)。

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

## 一之二、让技法自己跑

名片里加 `trigger`，这条技法就不必等模型下令：

```python
TacticInfo(name="deploy_mcv", summary="把未展开的基地车展开",
           trigger=Trigger.every(30))          # 每 30 游戏帧看一眼
TacticInfo(..., trigger=Trigger.on("low_power"))  # 那个事件来了才跑
TacticInfo(..., trigger=Trigger.automatic("low_power", every_frames=90))
```

**自动触发产出的是脉冲**：跑一次、下发一次、不建编队。所以它不会长期占着单位的
租约，也不会有 `Produce` 每拍重发的风险。要持续控制单位的技法（推进、缠斗）仍要
由模型显式 `call`。

三条规矩：

1. **不能有必填参数**，否则登记时就报错——自动触发时没有人填。
2. **门槛一样管**：等级、停用名单、适用条件，自动触发与模型调用走同一条受理路径。
3. **自己判断该不该动**。自动触发命中不等于该做事，`run` 里判完可以返回 `()`：
   空转是正常的、不报给模型的；只有真下发了意图或出错才会出现在 `status` 里。

实体清单见 `src/ra2agent/tactics/builtin/opening.py`。

### 叫醒模型

自动层多数时候不该打扰模型。真到了**只有模型能决定**的事（该扩张还是该防守、
这笔钱怎么花），返回一条 `Wake`：

```python
from ra2agent.runtime.intents import Wake

return (ctx.intent(Wake, text="基地被打了，3 个建筑在掉血"),)
```

它**不落到引擎**——技法层把它拦下来交给唤醒桥，其余意图照常下发。

三条节制（都在库里，不必自己写）：

- **限流**：两次唤醒之间至少隔若干游戏帧；
- **合并**：被挡住的内容不丢，攒进待发队列，下次并成一条投出去；
- **额度**：一局最多唤醒几次。**一次唤醒就是一轮 LLM 调用**，写歪的策略会烧掉一整局的额度。

所以：**能不叫醒就不叫醒。** 多数事让技法自己做完，`Wake` 只留给真正需要判断的。

送成功的唤醒不会出现在 `status` 里（那条消息本身就是通知）；**没送出去的会报**——
静默丢事件比报错糟得多。

## 二、允许的 import

白名单：`math`、`typing`、`dataclasses`、`enum`，以及本项目的
`ra2agent.runtime.intents`、`ra2agent.runtime.formation`、`ra2agent.constants`、`ra2agent.engine.state`。

禁止：`os`、`sys`、`socket`、`subprocess`、`importlib`、`time`、`random`、
`open`、`eval`、`exec`。要随机或计时就说明用法错了——技法必须是确定性的。

## 三、上下文 API

| 成员 | 是什么 |
|---|---|
| `ctx.observation` | 一帧经迷雾过滤的观测；`map_data`、`visible_enemies`、`state` 都在这 |
| `ctx.subject` | 本层管的编队（只读）：`agents()` 本次该管的单位、`object_of(id)`、`agent_id(pointer)`、`cell_of(id)`。**`subject` 有两种形态**，见下 |
| `ctx.params` | 本次调用的参数，已按名片补好默认值 |
| `ctx.frame` | 当前游戏帧 |
| `ctx.attempt` | 第几次尝试；卡住重来时由运行时递增，用来换落点。**脉冲恒为 0** |
| `ctx.memo` | 跨帧记事本，按「技法名 + 键」隔离。**编队任务结束清空**；自动脉冲共用 Autopilot.memo，可跨拍保存冷却，按技法名与键隔离 |
| `ctx.call(name, **params, optional=False)` | 调另一条技法 |
| `ctx.intent(cls, **payload)` | 按信封约定造意图 |
| `ctx.types` | 对象类型表；没取到时为 `None` |
| `ctx.type_pointer(name, rtti=None)` | 类型名 → 指针，找不到给 `None` |
| `ctx.intent(cls, scope=None, **payload)` | 造意图；没给 `scope` 就用本队单位，一个都没有时用空归属 |
| `ctx.remember(key, value)` / `ctx.recall(key, default)` | 记事本的读写糖 |

**`subject` 的两种形态，写法要同时适配：**

- 模型 `call` 受理时它是 `UnitPool`——己方对象的全池；Commander 的自动脉冲默认用排除在管单位的 `UnitPool`，发送前再检查租约。待放置建筑可通过 `pending()` 寻址，但不出现在 `agents()`；独立使用 Autopilot 时主体和 available 由调用者提供。
- 技法在编队任务里真跑起来时，它是 `Squad`——**只有这条任务名下的单位**，没有 `pending()`。

**能用 `ctx.observation` 判的就别碰 `subject`。** 碰了要保证两种形态下都对：只认
`UnitPool` 的写法（例如调 `subject.pending()`）会让技法受理通过、运行时却永远调不动。
需要单位名单时用 `ctx.subject.agents()`，它两边都有。

**自动触发的 subject 不是所选编队**。Commander 默认排除在管单位，但没有 Agent 租约的玩家行为、原生任务仍可能正在运行；自动技法应按合法观测筛选，不能把“没有租约”解释为“没有任务”。从 state 枚举对象时，也要确认对应 Agent ID 在 `subject.agents()` 中，避免给已排除单位生成意图并消耗冷却。

## 四、能返回的意图

| 类 | 载荷 | 说明 |
|---|---|---|
| `MoveTo` | `units`、`cell`、`stance` | 移动；`stance` 取 `aggressive` / `passive` / `hold` |
| `Hold` | `units` | 旧 Mission_Stop 兼容路径，不承诺玩家 S 等价 |
| `Stop` | `units`（单个己方车辆 Agent ID） | 实验 Stop v1；一次玩家 Idle 输入，当前离线/构建通过，Grizzly 限定真机通过，其他型号未验，见[Stop 验证](../../notes/验证/Stop玩家接口验证.md) |
| `GuardCurrent` | `units`（单个己方车辆 Agent ID） | 实验 Guard v1；一次原版 G 输入，当前位置由 DLL 执行时确定；回执不承诺后续效果 |
| `GuardPosition` | `units`（单个己方车辆 Agent ID）、`cell` | 实验 Guard v1；一次地点警戒输入，确认不表示已到达或持续保护 |
| `EscortUnit` / `GuardStructure` | `units`（单个己方车辆 Agent ID）、`target`（己方车辆 / 建筑 Agent ID） | 实验对象警戒 v1；目标不占 actor 租约，新输入确认后释放管理；DLL 未部署 / 真机未验，见[验证](../../notes/验证/对象警戒接口验证.md) |
| `Attack` | `units`、`target` | 攻击指定对象 |
| `Produce` | `type_pointer`、`type_name` | 开始生产 |
| `Place` | `building`、`cell` | 放置已完工建筑；`building` 是 **agent id**，完工待放对象只有 `ctx.subject.agent_id(pointer)` 认得 |
| `Sell` | `buildings` | 变卖建筑 |
| `Deploy` | `units` | 展开基地车（走 `ClickEvent`，不是 `UnitOrder`） |
| `Wake` | `text`、可选 `placement_building` | **不落到引擎**：请求唤醒模型；放置通知可关联己方建筑 Agent ID，不传 pointer / native_id。同批合并投递，分别过期，见[时效验证](../../notes/验证/放置通知时效验证.md) |
| `TacticCall` | `tactic`、`params` | 指挥层意图，不是你要返回的东西——它是模型 `call` 的载荷 |

Guard 首版只有限定新 DLL 场景通过，具体已验证对象、适用性与剩余边界见[Guard 接口验证](../../notes/验证/Guard接口验证.md)。未经声明 v1 的 DLL 会被 L0 明确拒绝；禁止为新意图自行连接 Client、开放任意 Mission 或每拍重发。S4 的正式 native_guard、CMIN 采矿兼容分支和自动冷却已最小接入，证据与长期启用边界见[Guard 技法迁移验证](../../notes/验证/Guard技法迁移验证.md)；持续任务与完整迁移仍未完成。

### `Wake` 的节制

一次 `Wake` 就是**一轮 LLM 调用**，而一局有额度上限、两次之间还有帧数限流。故：

- **常规失败原因不要用 `Wake` 传**——那是每拍都能算出来的事实。任务失败的原因会随
  `status` 的「新结果」报给模型（带 `reason`），不需要你再叫一次。
- `Wake` 只留给**只有模型能决定**的事：该扩张还是防守、这笔钱怎么花。
- 被限流或失败的有效内容留在待发队列，后续请求合并投出，不主动重试。关联放置通知可由已有观测判定过期；普通及旧无关联通知按时间期限处理，同批说明只合并投递一次。

### 空单位：目前做不到

`call` **必须点名至少一个己方单位**（`Commander._check_units`），而生产、建造、变卖
这类**阵营级动作不针对任何对象**。框架里 `ctx.intent` 已经支持无归属（`Scope.empty()`），
但 `call` 这条入口还没接上，故现在只能：**用 `units` 点名一个相关建筑**（例如让某个厂
来造），意图再带上这些 id。这是框架限制，不是设计意图；别为此把技法写成依赖具体厂的
样子。

**对象一律用 Agent 侧 id**，不是引擎指针——指针在单位变身时会变。引擎指针转 id
用 `ctx.subject.agent_id(pointer)`。

### 造东西：先解析类型指针

`Produce` 要的是 `type_pointer`，用 `ctx.type_pointer(名字)` 解析。名字可以是**注册名**
（`MTNK`）或**英文显示名**（`Grizzly Battle Tank`），注册名要跑起来的进程挂过别名
（默认从 `corpus/derived/rules.json` 挂）。

**解析不到就放弃**，不要拿个假指针去下单：

```python
pointer = ctx.type_pointer("MTNK")
if pointer is None:
    return ()          # 类型表里没有，这一拍什么都不做
return (ctx.intent(Produce, type_pointer=pointer, type_name="MTNK"),)
```

名字查 `codex/units.md` 与 `codex/buildings.md`。

意图必须用 `ctx.intent` 造，它会自动填 `layer`、`created_frame` 与 `scope`：

```python
return (ctx.intent(MoveTo, units=ctx.subject.agents(), cell=(40, 40)),)
```

## 五、名片

```python
Tactic(TacticInfo(
    name="advance_to_cell",              # 唯一名，模型按它引用
    summary="把这队单位推进到目标格附近",   # 一句话，进卡片
    params=(Param("cell", REQUIRED, "目标格 (x, y)", is_cell),
            Param("stance", "aggressive", "姿态", is_stance)),
    requires=("has_units", "has_map"),   # 适用条件
    level=Level.NORMAL,                  # 等级，见下
    expose=True,                         # 是否进对战时的卡片
    version=1), run)
```

条件名见 `tactics/conditions.py`，目录如下（不够用时去那里加，**不要在技法里偷偷判断**）：

| 条件 | 判什么 | 要参数 |
|---|---|---|
| `has_units` | 这一队至少有一个可用单位 | |
| `has_map` | 已有底图 | |
| `stop_v1` | GameState 声明 Stop 接口版本恰为 1；不含效果保证 | |
| `guard_v1` | GameState 声明 Guard 接口版本恰为 1；不含具体单位适用性 | |
| `object_guard_v1` | GameState 独立声明对象警戒 v1；不借旧 Guard 能力 | |
| `own_guard_vehicle_target` / `own_guard_building_target` | 当前合法己方目标类型、存活和身份；从 observation.own 寻址，不要求目标属于 actor Squad | ✓ |
| `has_enemies` / `no_enemies` | 当前看不看得见敌人 | |
| `has_pending_building` | 手上有完工待放置的建筑 | |
| `has_construction_yard` | 己方有一栋建造厂 | |
| `has_factory` | 己方有生产队列条目 | |
| `cell_explored` / `cell_unknown` | 参数里的格已探索 / 未探索 | ✓ |
| `can_afford` | 参数点名的类型买得起（价格从类型表取） | ✓ |

**参数型条件的两条限制**：

1. **卡片筛选时没有参数**（`tactics` 这个工具不带参数），故这类条件**不会让卡片消失**，
   只在 `call` 受理与技法真跑时生效。别指望靠它把用不上的技法从卡片里藏掉。
2. 条件拿到的参数是**补好默认值的那一份**（受理时先过 `check_params`），故 `Param`
   的默认值要能代表"不填"的语义；`None` 这类默认值要给参数挂 `is_optional_cell`
   这样的检查，否则 `is_cell` 会把默认值判成非法。

**条件会在两种 `subject` 下各判一次**（受理时 `UnitPool`、运行时 `Squad`）。能用
`ctx.observation` 判的就别碰 `subject`，否则要两路都写对。

**每个参数都要挂取值检查**，内置的有 `is_cell`、`is_optional_cell`、`is_stance`、
`is_non_negative_int`、`is_positive_number`。只声明 `Param` 会漏掉形状错误：
`cell: null` 会一路走到你的函数里才炸，模型拿到的是一句看不懂的 TypeError。

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

**还要有一条走 `Commander.call`。** `registry.run` 是**直调**，它绕过了卡片筛选、
`_check_units`、租约（`_taken`）与 `check_params` 的真实次序——而"技法受理通过、真跑
起来却永远调不动"这类问题**只在那条路上暴露**。至少断言一次：

```python
result = commander.call([CallRequest(tactic="mine", units=(agent,),
                                     params={...})])[0]
self.assertTrue(result.accepted, result.error)
```

跑全套：`PYTHONPATH=src python3 -m unittest discover -s tests -t .`。

## 九、注册

新技法先放 `src/ra2agent/tactics/local/`（该目录被 `.gitignore` 排除，不入库），
验证通过后再并入 `tactics/builtin/`，并在 `builtin/__init__.py` 的 `TACTICS` 里汇总。
等级、条件或参数有任何一处说不清，就退回草稿。

**注册进库之前先问一句：它在两种 `subject` 下都跑得动吗？** 未注册的草稿只被
`registry.run` 直调过，而注册之后模型会从 `call` 进来——那才是 `UnitPool` 那一侧。

## 十、禁止清单

- 直接发命令、直接调 `Client`、直接改 `GameState`。
- 读写文件、网络、进程、时钟、随机数。
- 捕获异常后当作没发生（要就让它抛，运行时负责隔离与记录）。
- 一次产出几十条命令（意图上限 32，超了直接拒绝）。
- 把「什么时候该用」藏进代码却不写 `requires`。
- 用 `Wake` 传常规失败原因（那是每拍可算的事实，浪费整局额度）。
