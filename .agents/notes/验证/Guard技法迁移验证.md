# Guard 技法迁移验证

日期：2026-10-02。对应[演进计划](../设计/L1基础能力与技法演进计划.md) S4 的 Guard 最小接入；不代表全部基础操作、长期任务与技法迁移完成。底层契约、DLL 指纹、原版效果及未测服务端边界以[Guard 接口验证](Guard接口验证.md)为准。

## 接入与兼容

| 技法 | 当前行为 | 承诺与边界 |
|---|---|---|
| native_guard v1 | 单个己方车辆；cell=None 构造 GuardCurrent，给出 cell 构造 GuardPosition | requires=has_units/has_map/guard_v1；只在已声明版本 1 的局面展示与受理；0、未知版本或缺地图拒绝，禁止试发探测 |
| harvest v2 | 目录 Entry.id=CMIN 且接口版本 1 时使用 GuardCurrent；其余情况维持 MoveTo(passive) 至最近已探索矿格 | 保留旧名称、无新增参数、has_units/has_map 和 idle_ends_task；v1 身份缺失由 L0 拒绝，不以旧移动掩盖异常；未单独提供 HarvestAt |
| auto_harvest v2 | 同一恢复路径，每 60 游戏帧评估停工矿车 | 保留原触发与可见性；跳过采矿、移动、返厂、卸矿和 AREA_GUARD；不重新定义其他经济技法 |
| guard_area | 保持 Python 按半径选择可见敌人并发 Attack，以及原有 radius/max_frames | 不改名，不替换为原版 G，不宣称修复其全部长期控制边界 |

native_guard 将两个地点形态合并在一张卡片中，未增加 MCP 工具。单位数量、己方归属、存活、变身状态、native_id 与实际坐标仍由生产 L0 校验；Commander 条件检查使用全池，因此多个单位、步兵或缺原版身份可能先受理，再在执行时明确失败，不能把 accepted 当成适用性通过。多单位 native_guard 构造一条请求，由单对象约束整体拒绝，未实现逐单位结果或批量警戒。所有模型动作仍通过技法 → Commander → MicroLayer → Executor。

## 生命周期与自动恢复

native_input_observed 仅确认原版输入。MicroLayer 记录 completion_basis=operation_observed 后结算并释放租约，ARRIVED 不表示地点到达、维修完成或持续保护。游戏 AI 可以继续执行，也可能被后续玩家操作或其他技法覆盖；native_guard 不持有长期控制权。cancel 仅撤销在管任务，不发 Stop；已结算任务不可再次取消。需要终止单位行为时，另行调用已有 hold_position；自动经济仍可能随后恢复停工矿车，尚无“停止并抑制自动恢复”的持久策略。

auto_harvest 的冷却按 Agent ID 记录 (frame, (intent.kind, cell))，同一恢复操作间隔至少 600 游戏帧。GuardCurrent 不依赖位置，因此位置变化不解除冷却；旧 MoveTo 的目标矿格变化仍允许重新选矿。已消失身份剪枝，同地址的新身份不继承冷却；仍存在的己方对象在短暂 limbo 中保留冷却。在管单位从自动主体排除时不产出意图、不消耗冷却，发送前仍检查 available，避免租约竞争。

Autopilot 使用共享 memo，按技法名与键隔离，脉冲重建上下文不清空该记忆；此前 skill 中“每拍空记事本”的描述与代码不符，已修正。冷却在生成意图时记入，不能当成实际发送或效果证据。已发送但结果未知的请求由现有 pending 机制阻止重发，即使冷却到期也只等观测；本轮未新增失败自动重试或按效果重新下 G 的策略。

## 离线验证

新增 tests/test_guard_tactics.py 的 20 项测试，使用正式 builtin 名片：覆盖 UnitPool 与 Commander.call → Squad → 真实 Executor、两种地点形态、卡片版本门、缺地图/状态/空单位/非法参数、L0 对身份和单位类型的拒绝、输入确认与租约释放、cancel 不发送 Stop、真实未知结果及迟到匹配不重发、采矿兼容分支、实际 Autopilot 脉冲冷却、AREA_GUARD/往返不覆盖、占用排除、同指针身份变化与短暂 limbo。采矿目录与类型表沿用 proto 夹具；不能据此宣称 HARV 真机通过或已取得 FV 动态载员状态。

当前改动相关回归 657 项通过，命令如下；未运行与本轮无关的全项目测试。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest \
  tests.test_guard_tactics tests.test_tactic_actions tests.test_field_tactics tests.test_tactics \
  tests.test_guard_fault_transport tests.test_guard_interface tests.test_identity tests.test_intents \
  tests.test_payloads tests.test_wire tests.test_validate tests.test_state tests.test_native_events \
  tests.test_executor tests.test_micro tests.test_autopilot tests.test_command tests.test_mcp tests.test_replay
```

## 正式技法真机接线

记录：.agents/tmp/engine-build/backups/guard-s4-20261002-200034/validation.json，status=passed。临时驱动为 .agents/tmp/engine-build/guard_s4_check.py 与 guard_s4_probe.py，复用既有备份、替换、启动与 finally 恢复流程；正式 builtin 仅取 native_guard 一条注册进隔离 registry，无自动经济，不需要人工准备单位。使用与 S3 相同的已编译 Guard v1 DLL，未修改 DLL、协议、DSH 或系统依赖。

| 操作 | 参数 | 提交 / 观测帧 | command_id | 回执 |
|---|---|---|---|---|
| current_initial | cell=None | 318 / 322 | 39 | observed_match / native_input_observed |
| position | cell=(25,80) | 347 / 351 | 46 | observed_match / native_input_observed |
| current_at_destination | cell=None | 462 / 467 | 57 | observed_match / native_input_observed |

Alpha 操作 Grizzly：Agent ID=224，native_id=1043819，初始 cell=(30,80)。Beta 对应对象按阵营数组索引、类型与精确世界坐标配对，未向 Beta 下令。三个输入逐次确认并释放租约；地点到达单独观察，最终 Alpha frame=557 / Beta frame=559 的对应对象均 cell=(25,80)、Mission=AREA_GUARD、HP=300。两次采样并非同帧，CRC 也不同，不能据此声明完整联机同步。

下令前只读等待两侧游戏帧推进且 Alpha frame>300，最长 120 秒；短暂切屏停帧不直接判定接口失败。原生输入未知时不重发。测试中检查崩溃报告变化；结束后驱动恢复六个原文件的存在性与哈希、DLL 硬链接，关闭连接和本轮进程。随后独立复核恢复哈希、硬链接、端口 14521/14522、游戏进程及 EXCEPT_CNCNET.TXT/except.txt，均通过且崩溃报告未新增。该验证结束时两侧恢复原 DLL，guard_v1 门关闭；后续经用户确认的长期部署与现行状态见[部署记录](../环境/Guard部署与联调.md)，临时测试本身不构成长期启用授权。

## 复用经验与下一步

迁移原生行为时，先分离 Agent 持续控制与一次输入，再保留旧名的明确兼容分支；已验证型号优先使用原生 AI，未验证型号不升级结论。回归应同时验证真实名片、实际受理链与自动层记忆；新增薄包装在底层未改时可复用原有效果证据，再补少量正式入口真机输入，不必重复全套人工准备。

CMIN 采矿循环和 Engineer-FV 维修效果沿用[Guard 多态记录](Guard接口验证.md#车辆多态补测限定正例通过)，本轮未重新进行 harvest/auto_harvest 在真实矿车上的接线与长期观察，也未重复新接口空 FV 或 HARV 对照。FV 无动态载员/武器模式回读，因此 native_guard 不承诺维修，不新增保证维修的技法。

长期启用已按用户确认完成，现行状态、持久备份和回滚入口见[部署记录](../环境/Guard部署与联调.md)。普通 MCP/DSH 的四项限定卡片、输入与 CMIN 显式/自动恢复联调已完成并收尾，结果与采样经验见[联调验证](GuardDSH联调验证.md)；后续单位准备继续允许人工协作，非必要人工对照不重复。不以完整 idle/dispose 或无头体系为前置条件，不能因共享 MCP 的一次短任务通过而升级玩家子 Agent 冷恢复结论。

持续暂停恢复未验证，S 是停止单位而非游戏暂停；完整 DSH idle/dispose、对象护送、建筑保护、所有车辆多态、完整跨局身份与请求契约、持续护送/路径和长期对局可靠性仍未验证。Beta 为 Americans；保留用户关于切屏全局短暂卡顿的反馈，不把 Tab 当成已证实的原因。
