# Move / Stop 接口离线验证

日期：2026-10-02。范围：现有 Python 执行链的安全与结果表达；未启动游戏、修改 DLL 或 DSH 配置，未验证原版 Guard / Escort / Harvest 行为。

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

本轮工作树执行上述入口：322 项通过；git diff --check 无格式错误。未执行全量测试。

这些测试使用 FakeClient、FakeExecutor 或固定观测。覆盖新鲜状态下对象消失、归属变化、TTL、身份重映射、帧回退和玩家边界、既有匹配证据、未知结果保留与延迟匹配、重叠租约、自动层避让、越界 actors / scope、部分损失、Move / Stop 完成条件及 MCP 同帧恢复。通过只表示这些 Python 边界符合断言，不表示真实引擎执行正确。

## 3. 下一轮最小真机验证

先按[真机测试手册](真机测试手册.md)确认实际宿主、单一写入者与帧推进。用户可准备同一局中少量己方载具与空地，先验证普通移动的提交、destination 回执和到位是否分开；再验证已停止时再次 Stop 的 preexisting_match。暂停后不应产生新的自动提交，恢复后先采样最新状态；提交后暂停的既有命令仍可能执行，不把它当新请求。

Move / Stop 闭环确认后，按[玩家操作能力表](../引擎/玩家操作能力表.md) T01–T04 对照人类 G、保护 / 护送、矿车与维修 FV。准备单位、选择、按键和画面判断可由用户完成；Agent 记录必要帧和状态即可，不以无头化或完整录屏为前置要求。

## 4. 待补能力

可靠局次 ID、尝试 ID、完整逐单位执行回执、对象目标可见性与动态能力检查、Target / Follow / 乘员 / 货量回读、明确对象消耗归因以及 DSH idle / dispose 后持续运行仍未实现或验证。具体候选契约见[接口审计](../../drafts/接口/L1基础接口契约与现状审计.md)，阶段状态见[演进计划](../设计/L1基础能力与技法演进计划.md)。
