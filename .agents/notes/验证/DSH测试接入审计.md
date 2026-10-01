# DSH 测试接入审计

日期：2026-10-02。只读调查本项目 Python/TypeScript、本机 DSH 源码与安装记录；未运行测试、启动游戏或服务、调用真实模型、安装依赖或修改配置。已知差距与方案建议在本文留档，不能视为已经修复。基础接口契约见[L1 审计](../../drafts/接口/L1基础接口契约与现状审计.md)，实施顺序见[演进计划](../设计/L1基础能力与技法演进计划.md)。

## 1. 结论

DSH 是模型侧的接入宿主，底层引擎客户端、L1 技法、意图/执行器、回放和 MCP 协议都可脱离真实 DSH 服务及模型验证。新基础接口先做 Python 离线验证和独占游戏实例的原版对照，DSH 放在玩家会话、隔离、空闲生命周期、唤醒与恢复的独立验收阶段。

现有项目已经有 Python unittest 和 DSH 插件集成测试入口，不需要为首批底层能力更换 agent 宿主。但是当前玩家子 agent 的 MCP/任务寿命与 agent scope 耦合，冷玩家唤醒路径静态上不闭合，需要在依赖无人值守持续任务之前处理。

## 2. 两种接入方式的生命周期

| 方式 | 当前结构 | 对测试的影响 |
|---|---|---|
| 普通 ra2 preset | dsh/cordis.patch.yml:147 挂一份默认 MCP；DSH preset generation 激活时挂载一次，只有 retired 且 users==0 才释放 | 同一 generation 的多个会话共享 Python GameSession、任务、Commander 结果游标；不能当互相独立的测试控制器 |
| dsh-players 玩家子 agent | 每玩家独立 serverName、--player 与 --wake-session；MCP 挂 agent 自己的 scope，dispose 时关闭，冷恢复重新挂载 | 玩家模型回合结束并释放 agent 后，原 Python 任务与自动层可能消失；客户端 reconnect 不等于任务持久化 |

普通 preset 不必随某个模型回合结束退出；不得把玩家子 agent 的释放现象泛化为所有 DSH 接入。本机 DSH 依据：/home/youthz/deepseek-harness/packages/preset/agent-preset-registry/src/index.ts:102–112、144–147。玩家挂载依据：dsh-players/src/index.ts:284、430–453；src/players.ts:332。

DSH 的玩家子 agent 与此次用于源码调查的 Codex subagent 属不同宿主和生命周期。测试控制器可以由调查 subagent 执行，但不能据此假定已经验证 DSH 玩家 agent 的工具、隔离或冷恢复。

## 3. 游戏任务不应依赖模型正在运行

GameSession._connect 创建 Observer/Executor/MicroLayer/Commander 并启动线程（mcp.py:250–281）；reset/close 会丢弃任务与连接（:229、307）。既有原版命令可能继续执行，但 L1 的监测、恢复、策略和自动经济不会随 watcher 接续。

watch.py:48–85 只读局势、合成事件和投递唤醒，没有 MicroLayer、Commander 或任务管理。它能维持事件侦测，不能作为持续技法的常驻执行器。已有文档“模型空闲时技法仍推进”的承诺，在玩家 agent scope 释放的接入方式下缺乏保障。

建议将 L1 生命周期归对局常驻服务，模型连接作为客户端：任务、租约、请求回执与局次身份由服务持有，模型 idle/dispose 不终止任务；用显式 player/session 绑定接入 DSH。此为架构建议，尚未设计最终传输与部署，也未实施。

可比较两种落地路径：A. 把现有 GameSession 核心托管为对局常驻进程，stdio MCP 作为轻客户端；B. 先将玩家专用 MCP 挂更长寿的明确席位作用域并维持唯一控制者。B 实现可能更少，但不能把玩家隔离、会话重启和任务恢复交给隐式 preset 共享。选择前应先写生命周期验收，避免为每种宿主复制一套 L1。

## 4. 唤醒路径与冷玩家断口

当前链路为 Observer/事件 → WakeBridge → HTTP POST /ra2/wake → DSH followup → sessions.flush → 模型新回合。WakeBridge 会限流和合并，并识别 HTTP 200 下的 ok:false；成功必须检查响应体而非 HTTP 状态。依据 wake.py:136、159–172，dsh-wake/src/binding.ts:124 起。

活跃玩家子 agent 可以 ctx.agents.get(id).followup，然后确认 sessions.flush（binding.ts:136–143）。不存在于 live registry 的冷玩家子 agent 会落到普通 sessionController.resolveAgent（:145–148）；本机 DSH session-controller 的 packages/api/session-controller/src/agent.ts:80–101、190–191、428–429 明确拒绝 origin=subagent，要求 subagent delivery。这条冷玩家路径静态上不闭合；普通会话冷恢复和玩家子 agent 冷恢复应分开验收。

现有 dsh-wake/tests/wake.test.ts 使用本机 DSH 类库和替身模型/agents，不能证明真实已结算玩家 child 的恢复。应对接宿主已有的 subagent continuation/delivery 机制，明确 descriptor、工具过滤与 player 绑定的恢复，并补充该场景。仅再次发送同一 HTTP 请求不能自动修复路由缺失。

验唤醒期间不读玩家 status、不向玩家发普通消息，也不使用会触发 followup 的协作动作；这些操作会消费结果或污染唤醒判据。只看 source.kind=ra2-wake 的持久化消息与新的模型回合，并关联事件/请求和席位。

## 5. 暂停与多连接

MCP 已增加活动对局、有效席位及游戏帧推进门控，同帧不执行技法，边界变化丢弃旧任务；同帧 / 恢复 / 退帧 / 新席位离线回归通过。实现证据及读取到发送间的竞争窗口见[Move / Stop 接口离线验证](MoveStop接口离线验证.md)。本轮未验证真实 DSH 宿主或焦点暂停，MCP / 玩家 agent / watcher 的生命周期限制不因该修复消失。

现有手册中“模型已连接，其他脚本只能等 DSH 退出再连”不能当一般规则。调查上游支持多个 socket：ra2yrcpp/src/constants.hpp:12 的 MAX_CLIENTS=16；websocket_server.cpp:89–100 按有效配置限数；instrumentation_service.cpp:157–165 为每 socket 创建结果队列。本机两份 ra2yrcpp.json 显式端口与名册相符，未显式 max_connections；部署 DLL 的版本、默认限数和并发稳定性未实测。

允许 MCP 与 watcher 多个只读连接是否可靠应单独验证；即使多连接成立，每个实验实例仍只能有一个命令写入者。Client 不是线程安全，GameSession 通过 RLock 序列化；不同连接/进程的锁不能仲裁同一单位。焦点暂停取决于 DDrawCompat/cnc-ddraw 和实例配置，不能仅凭端口隔离宣称能并行跑两个实验。

## 6. 已找到的静态缺陷与文档差距

| 项目 | 证据 | 后续处理 |
|---|---|---|
| watch 异常分支未导入 Ra2Error | watch.py:67 使用名称但文件没有 import；当前 test_watch 主要覆盖正常事件 | 补异常路径测试并修复，当前未运行触发验证 |
| 冷玩家子 agent 唤醒无法走普通 resolver | binding.ts:145；DSH resolver 拒绝 subagent | 使用专用 continuation/delivery，测试完整释放后恢复 |
| watcher 不推进 L1 | watch.py:48 | 对局服务持续运行契约，勿仅靠 watcher 宣称任务继续 |
| MCP 游戏帧门控 | mcp.py:GameSession._advance | 已实现并通过离线边界回归；真实宿主、暂停恢复待验 |
| 玩家认领表只在内存 | dsh-players/src/players.ts:166 起 | DSH 重启后 player/child 恢复策略需明确 |
| 玩家工具边界文档自相矛盾 | dsh-players/README.md 前面说明屏蔽 bash/派生等，后面旧“边界”段却称照旧可用 | 以 src/players.ts 的实际过滤和执行守卫为准，实施时修正文档 |
| 通用文档混用 MCP 生命周期/连接约束 | 指挥层、真机测试手册、watch 模块说明 | 区分普通 preset、玩家 agent、历史部署限制 |

本项目相关 lib 生成物存在。玩家挂载关键逻辑在 lib/index.js:189–199、306–329，冷唤醒逻辑在 dsh-wake/lib/binding.js:76–94 也存在；未发现这些关键逻辑的 src/lib 差异，但未做完整构建一致性验证。实际 loader 加载 lib，未来修改 TS 后须记录构建版本，不能只修改 src 并声称已部署。

## 7. 本机准备状态与未知

仅检查安全字段与路径：~/.dsh/profiles/web/package.json 的 bundle 列表包含 @local/ra2-preset、@local/ra2-wake、@local/ra2-players，依赖指向本项目；/home/youthz/deepseek-harness 源码与 node_modules/.bin/tsx、tsc 存在；两份探针目录 /mnt/d/Games/ra2probe、/mnt/d/Games/ra2probe-b 中的配置端口为 14521/14522。

这些只证明文件和安装记录存在，不证明插件已激活、当前进程加载最新 lib/preset、握手成功、游戏在运行、wake 路由可用或 API/模型可调用。未读取凭据或完整会话转录。当前沙箱 /proc 可见性不足以可靠判定宿主 DSH 运行状态，不将其作为“DSH 未运行”的证据。

## 8. 分层测试入口（本调查全部未执行）

| 层次 | 现成入口 / 验证对象 | 依赖与不能证明的事项 |
|---|---|---|
| Python 契约与逻辑 | tests/test_intents、test_executor、test_validate、test_micro、test_command、test_autopilot | 标准库、替身状态/Client；无 DSH/模型/游戏，不能证明原生行为 |
| 离线回放 | ra2agent.replay 与 tests/test_replay | 固定录制、真实 plan 和合成 outcome；无真实 verify、寻路或命令因果 |
| MCP 协议 | tests/test_mcp 的 FakeSession/StringIO；后续可独立 stdio 子进程驱动 | 初始化、schema、错误隔离和工具分派；不证明 DSH 实际加载 |
| DSH 插件集成 | dsh-players/tests/players.test.ts、dsh-wake/tests/wake.test.ts | 本机 DSH 类库、mock provider/client；无付费模型/游戏，但可能启动本地监听和写临时文件 |
| 原版游戏接口 | 独立 Python 驱动 + Observer/Executor + 人类操作对照 | 无须 DSH；游戏进程/连接/焦点/版本必须可控，单写入者 |
| DSH 端到端 | 真实 ra2 preset 或 player agent、真实 MCP、模型与游戏 | 验工具隔离、空闲持续、live/cold 唤醒、断连与重启恢复；放在接口语义通过之后 |

Python 测试运行方式见开发环境文档，需要 PYTHONPATH=src；不能直接把源码目录当已安装包。独立 MCP 的 python3 -m ra2agent.mcp 同样需要该环境或等价安装。dsh-players/package.json 和 dsh-wake/package.json 提供 test 脚本，使用本机 tsx 与 tsconfig.test.json；此次只读取入口，不执行 npm/pnpm、build/typecheck/test，也未安装包。

## 9. 验证层次与分工

1. 现有 Move / Stop 的首轮 Python 安全实现与离线回归见[接口离线验证](MoveStop接口离线验证.md)；C01–C09 中完整请求类型、可见性、动态能力及对象归因仍需补齐。
2. 由唯一执行者串行完成能力表 T01–T04 原版对照；源码调查、准备场景和事后日志分析可并行，输出目录分开。
3. 用独立 stdio MCP 验完整协议分派，确认工具和后台线程的生命周期；无需先开 DSH 模型会话。
4. 补 DSH 插件级 cold player、scope dispose、恢复过滤/归属、watch 异常和多会话游标场景，再运行其已有集成测试。
5. 最后真实 DSH 端到端：玩家 idle 后 L1 是否继续；事件是否恢复正确 child；DSH 重启是否恢复正确席位；普通共享 preset 是否消费彼此结果；真实模型能否按卡片正确使用能力。

按实验需要记录宿主模式、源码/lib/preset 指纹、局次/席位、端口与渲染配置、唯一写入者和证据路径。每轮测试明确区分 passed/failed/not_run/inconclusive，记录游戏是否仍有未确认排队命令；自动层按实验配置停用或明确纳入，不让开局/经济脉冲污染单条操作结果。

## 源码入口

[MCP](../../../src/ra2agent/mcp.py)、[watch](../../../src/ra2agent/watch.py)、[唤醒桥](../../../src/ra2agent/wake.py)、[回放](../../../src/ra2agent/replay.py)、[DSH preset](../../../dsh/README.md)、[玩家插件](../../../dsh-players/src/index.ts)、[玩家作用域](../../../dsh-players/src/players.ts)、[DSH 唤醒投递](../../../dsh-wake/src/binding.ts)。DSH 宿主源码位于本机 /home/youthz/deepseek-harness；行号为此次调查定位。

## 验证方法与更新

验证方式、人工协作与结论更新规则见[能力验证方法](能力验证方法.md)。待测项只在需要回答当前问题时执行，不作为每次改动的完整流水线；每项新证据先更新本文件的支持状态与限制，再回写相关计划。
