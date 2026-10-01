# Move / Stop 接口验证

日期：2026-10-02。范围：现有 Python 执行链的安全与结果表达。实现提交为 ed05e56（执行链）与 102e0e3（MCP），首轮文档提交为 cbbf0d7，结算帧修复提交为 b5eb758。当前已完成本步相关离线回归和下述真机验证；持续暂停恢复无法确认。未修改 DLL 或 DSH 配置，未验证新原版 Guard / Escort / Harvest 行为。

## 1. 实现与证据边界

| 环节 | 当前实现 | 限制 |
|---|---|---|
| 受理 | Commander 接收 TacticCall，Micro.assign 拒绝重叠租约 | 受理不表示已发送或完成 |
| 发送前复查 | Executor 每条 execute 读取最新 GameState，更新身份表，再检查局次边界、归属、存在、任务、坐标和 TTL | 玩家 pointer/index、stage 与帧回退用于边界检测，尚无可靠 match_id；不能消除读取与发送间的竞争窗口 |
| 提交日志 | command_sent 在客户端命令调用返回后记录；明确服务端拒绝另记 command_failed | 传输超时记 command_unverified，提交是否发生可能未知 |
| 观测回执 | ExecutionOutcome 有 receipt=observed_match、evidence、submitted_frame；发送前已匹配为 preexisting_match，否则为 state_changed | 两者均不证明本次命令导致变化；Move / AttackMove 共用 destination，Attack 仅看 Mission |
| 未知结果 | Micro 保留 pending 与 UNVERIFIED；同任务停止下令，后续谓词匹配记 late_match。Auto 保留该技法的 pending，未知期间不再触发提交，恢复匹配当拍也不重新发送 | 没有可用判据时只能等待任务期限、显式取消或会话结束；Auto 无任务 TTL，未匹配时保持阻断该技法；不提供引擎端去重 |
| 租约与作用域 | Commander 的 Auto subject 排除 Micro 在管对象；每条意图统一检查 scope 与实际 actors，发送前再次查询租约；Micro.assign 独立拒绝重叠 | Place 保留己方 completed Factory.object 的衍生对象例外；没有实现通用授权替换或跨进程仲裁 |
| 身份与完成 | Micro 每拍重新解析 Agent ID；全体完成才 satisfied，部分损失记 failed 并保留逐单位结果；命令关联父任务 ID | 缺席仍为 LOST，尚不能区分装载、死亡或消耗；身份变化沿用启发式表 |
| Move / Stop | 普通移动回执后继续等待位置；MoveTo(HOLD) 与 Hold 按 Stop 结算，不等待被忽略的目标格；结算保存逐单位 completion_basis | ARRIVED 仍为兼容状态名；其他旧操作沿用操作观测完成条件，尚未逐项重新核验 |
| 暂停与局次 | MCP 先 poll，活动对局且帧推进才 tick；同帧只更新观测。退帧、退出对局、玩家变化或席位异常丢弃旧任务，下次连接重建 | Micro.tick 是内部单拍入口，直接调用者仍须提供帧门控；DSH 进程生命周期及 watcher 行为未改 |
| 离线回放 | 合成回执标记 simulated / planning_only | 不发送命令，不运行真实 verify，不证明游戏效果 |

status 分别报告任务进度、最近命令回执及结果未知；取消或过期释放 Agent 任务不撤销已提交的引擎命令。Auto 的 pending 只阻断同一技法，不构成未知命令对象的全局租约；改派或其他技法仍需由实验执行者控制。

## 2. 离线回归

运行入口：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_executor tests.test_micro tests.test_autopilot tests.test_command tests.test_mcp tests.test_replay
```

本轮工作树执行上述入口：323 项通过；git diff --check 无格式错误。未执行全量测试。

这些测试使用 FakeClient、FakeExecutor 或固定观测。覆盖新鲜状态下对象消失、归属变化、TTL、身份重映射、帧回退和玩家边界、既有匹配证据、未知结果保留与延迟匹配、重叠租约、自动层避让、越界 actors / scope、部分损失、Move / Stop 完成条件及 MCP 同帧恢复。通过只表示这些 Python 边界符合断言，不表示真实引擎执行正确。

## 3. 本步真机验证结果

当前只验收上述提交改变的执行行为。相关六模块 323 项离线回归已通过，无业务变更时不必重复运行，也不要求全量测试。以下按实际场景记录结果；持续暂停恢复不因同帧采样通过而视为已验证。

| 编号 | 场景与操作 | 判据 | 当前状态 |
|---|---|---|---|
| M01 | 一台普通己方载具向空地执行 advance_to_cell，stance=passive、spread=0；目标距离足以区分移动中与到达 | call 先受理；command_sent / observed_match 与最终 satisfied 分开；completion_basis=goal_satisfied；行进中不重复下发 | 通过；回执帧 32660，目标完成帧 32755，单次提交 |
| M02 | 执行 hold_position，再对已停止的载具重复执行；同时检查 advance_to_cell 的 stance=hold 兼容路径 | Stop 不等待被忽略的目标格；完成依据为 operation_observed；仅发送前 Mission.STOP 已成立时标 preexisting_match，不能用画面静止代替 Mission 判定 | 通过；重复 Stop 为 preexisting_match；结算帧修复后复测通过 |
| M03 | 确认当前显示配置能暂停且 GetGameState 可读；冻结帧后受理一个移动任务，等待多个 MCP 轮询，再恢复 | 同帧无新 command_sent；恢复后依据新观测执行，正常行进中无重复提交；暂停判据是帧不变，不能仅看窗口失焦 | 部分通过；87 次真实同帧未 tick，33 次推进帧正常 tick；持续暂停恢复无法确认 |
| M04 | 将客户端等待预算临时缩短为 1 帧，真实提交 Move 后保留超时请求，继续观测 | status 报 unverified；同任务 / 同自动技法不因超时重发；匹配后 late_match；没有匹配时仍未知。恢复后原排队命令执行不计作新提交 | 通过限定场景；客户端预算 1 帧使真实提交后超时，单次提交后 late_match，恢复默认 45 帧 |
| M05 | 用已有 guard_area 的持续等待任务持有 MCV 租约，跨过 deploy_mcv 自动触发周期；不验证原版 Guard | 同对象在管时 Auto 不发送 Deploy；重复任务受理被租约拒绝；不以自动技法本来不适用作为避让证据 | 通过；持续等待任务持有 MCV，两次自动部署检查未下令，重复任务被拒绝 |
| M06 | 保留尚未完成的任务，由用户正常退出该局并进入新局，或观察真实可见的玩家 / 帧边界变化 | 旧任务丢弃，下一工具调用重建；旧 Agent ID / 请求不向新局发送；不声称能识别未被观测到的局次切换 | 通过；用户退出后丢弃旧任务，新局原会话重建且在管 0 项 |

本步按上述范围收尾，保留持续暂停恢复限制。M04 使用短等待预算的客户端测试策略，没有伪造游戏状态或新增故障注入框架；它证明真实提交超时后的观测恢复，不证明失焦暂停、传输中断或 Auto 非幂等命令已真机验证。默认等待预算已恢复。

### 环境与可追溯证据

使用名册中的 Alpha / Beta 两实例，探针端口 14521 / 14522，地图 144×144，FogOfWar=No、UnitCount=10、无 AI。Beta 不接收测试命令；运行独立 GameSession 的现有后台线程和 Commander / Executor，未启动真实 DSH 模型。临时进程内策略只开放本轮技法，M05 期间开放 deploy_mcv；WakeBridge 的 max_per_match=0，未投递唤醒。M03 在同一会话锁内调用真实 _advance，计数真实 tick，不替换 GameState。

运行 DLL 为 D:\Games\ra2probe\libra2yrcpp.dll，SHA-256 为 59b8d235a44398f20d290b44b60b92d7127fada1353cfe1d2bfd0a8b646a0b28。临时驱动与证据为 .agents/tmp/move-stop-validation/live.py、decision.jsonl、results.jsonl，不入库；本节保存恢复所需的摘要。

| 项目 | 请求 / 任务 ID | 关键证据 |
|---|---|---|
| M01 复测 | 506d2971d231 / de9757005474 | Grizzly Battle Tank 从 (30,71) 前往 (40,71)，在 (39,71) 按 1 格宽容完成；回执 32660，完成 32755 |
| M02 复测 | 515abbc64b22、498c80b646fb、094736aa780b | Stop 结算 / 回执帧分别一致为 32777、32783、32789；后两次为 preexisting_match，完成依据为 operation_observed |
| M04 | ac4f158533cf / 89db9dc8aa13 | 40054 提交；预算 1 帧、实际等 2 帧报未知；40072 late_match；40134 完成；该子请求 command_sent 总计 1 次 |
| M05 | 4bcb586c0a6c | Agent ID 233 的 MCV 在 32789–32848 保持在管；32812 / 32846 的自动部署均 intents=0；重复 hold_position 被拒绝 |
| M06 | 526464d8ec51 | 用户退出后 _broken=true、layer_discarded=true，原因“当前不是活动对局”；新局重连时帧 1733、在管 0 项，旧任务未恢复 |

### 发现与修复

初次 Stop 出现结算帧 13647 早于回执帧 13666。Micro 在同步执行返回后改用最新观测或回执状态更新结算帧；新增离线回归验证 100 帧受理、120 帧回执时结算为 120。修复后重跑相关六模块 323 项通过，并复测 M01 / M02，结算不早于回执。

首次 M05 使用 (14,92)，虽在 MapData 数组边界内，游戏仍返回 invalid cell。移动任务明确失败释放租约后自动部署，不能记作在管对象被抢占。复测改用已有 guard_area 持有等待任务，用户协助将建造厂收回 MCV 后通过。有效地图区域与数组边界的差异留待后续坐标合法性调查，不在本轮扩展引擎；新场景优先选择已知有效区域。

用户使用 S 停止选中单位，该操作不会停止游戏帧。当前 cnc-ddraw 的 noactivateapp=true 支持后台运行，采样帧持续推进；本轮没有取得持续冻结且 GetGameState 仍可读的场景。后续请求“暂停”须明确为游戏帧停止并先采样确认，不能将 S 或画面静止作为证明。

### 清理

测试驱动全部关闭，测试实例全部停止。两份 spawn.ini 已从 .render-bak 恢复并按字节比较一致，备份保留。游戏日志 / 录像和临时产物保留供诊断。未安装依赖、修改 config/match.json、替换 DLL 或修改显示配置。

### 准备与执行方式

先按[真机测试手册](真机测试手册.md)确认活动对局、端口、实际显示配置与单一命令写入者。使用当前代码的单独 MCP / GameSession 可验本轮链路，不要求真实模型或完整 DSH 会话；若使用 DSH，应先确认其 MCP 已加载本轮提交，不能把旧进程当作新代码。启动、重启 DSH、配置修改、日志写入与临时脚本创建均在实际操作前明确告知位置及目的。

最小用户准备为一台普通己方载具与可通行空地；M05 另需未展开 MCV；测试进程先停用自动部署，建立租约后再开放，以避免准备时自动展开。Agent 负责选合法格、通过既有技法受理与记录状态；用户可负责暂停 / 恢复、切换对局及目视结果。恢复焦点、日志路径与每个场景的停止条件在执行前确定，不要求同时录屏、完整包追踪或改显示配置。

M01–M02 只需排除干扰；M05 必须保留被测自动技法。实验中明确哪些自动技法会改变场景，不同时使用第二个写入进程。状态或日志不足以辨别预期行为时记无法确认，不根据任务名称推断效果。

### 留证与本步结束条件

每条记录至少包含提交版本、接入方式、场景、单位 / 目标、请求与父任务 ID、提交 / 观察帧、回执 evidence、任务结果及人工观察；只记录能够回答本场景问题的字段。临时产物放 .agents/tmp/ 下按本轮问题组织，创建前告知；结果回写本表或本记录，不另存重复状态源。

本步结束时汇总已通过、失败、未执行、无法确认。真机出现与本次改动有关的缺陷时只做对应修复和相关回归；剩余无法确认项保留为明确限制，不伪造验收通过。无论真机完成与否，当前会话不进入下一阶段，后续在用户压缩上下文后恢复。

## 4. 压缩后的恢复顺序

恢复时先读[交接](../../drafts/交接.md)的最新范围说明、本记录、[演进计划](../设计/L1基础能力与技法演进计划.md)，再按需读[接口审计](../../drafts/接口/L1基础接口契约与现状审计.md)和[DSH 接入审计](DSH测试接入审计.md)。以 git status / log 和最新测试记录为准；交接中的早期全量数量或完成表不能代替本轮验收。

本步相关验证已按限定范围收尾，M03 持续暂停恢复作为明确未确认项保留，不将其升级为全面暂停验收。压缩后按用户指令进入 S2 的玩家 Stop / G、保护 / 护送、矿车、维修 FV 对照测绘。后者验证新增原版语义，属于下一步，不在当前会话提前执行。可靠局次身份、完整请求契约和 DSH idle / dispose 生命周期也不在本轮顺带改造。

## 5. 待补能力

可靠局次 ID、尝试 ID、完整逐单位执行回执、对象目标可见性与动态能力检查、Target / Follow / 乘员 / 货量回读、明确对象消耗归因以及 DSH idle / dispose 后持续运行仍未实现或验证。具体候选契约见[接口审计](../../drafts/接口/L1基础接口契约与现状审计.md)，阶段状态见[演进计划](../设计/L1基础能力与技法演进计划.md)。
