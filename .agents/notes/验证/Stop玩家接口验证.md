# Stop 玩家接口验证

更新日期：2026-10-03。状态：A0 已完成 34 项覆盖矩阵与首组契约；A1 首个 Stop 切片已实现、离线回归和独立 DLL 构建通过，已完成 Grizzly 三项正例及 12 项服务端限定拒绝对照。两侧已按用户确认长期启用同一 Stop 产物，运行加载检查已通过：新局只读回读 guard_interface_version=1、stop_interface_version=1。计划与契约见[建设计划](../设计/玩家操作接口建设计划.md)和[接口审计](../../drafts/接口/L1基础接口契约与现状审计.md#a0-玩家能力覆盖矩阵)。

## 玩家语义核验与切片选择

[S2 T01-S](../引擎/玩家操作能力表.md#s2-现场记录)已记录 Grizzly Battle Tank 移动途中按 S，产生 Idle(type=6)，到达前停止并回到 GUARD。固定 ra2yrcpp `UnitOrderCtx::unit_action` 的旧 STOP 则调用 ClickMission(Mission_Stop)。两条路径不同，现有证据不足以证明全语义等价；旧停止测试也不证明玩家 Idle 等价，因此新增受控玩家入口，保留旧 Hold/MoveTo(hold) 兼容行为。

固定 YRpp EventClass 的 Data.Target.Whom 与协议 Event.Target.whom 匹配，协议字段 7 已存在；旧解析器未处理 Idle。新 DLL 对 Idle 回读该对象字段；其他事件不按 Idle 解释，残留 oneof 不参与匹配。固定 ABI 的 ClickEvent(0x6FFE00) 接受对象和事件类型；新入口选用 Idle，返回 false 时明确拒绝。此源码依据与编译不能替代新路径效果实测。

## 已实现契约

正式薄技法 `stop` → Stop 意图 → Executor/Validator → UnitOrder.PLAYER_STOP(action=15) → DLL 游戏线程复查 → ClickEvent(Idle)。模型仅调用技法，不增加原始事件工具。卡片标明 Grizzly 已验及其他型号未验，requires=has_units/has_map/stop_v1；当前 Guard DLL 未声明 stop_interface_version=1 时隐藏卡片并拒绝调用，不降级到旧 STOP。

首版每条意图及每次技法调用只接受一个己方车辆；首个效果验收对象限定 Grizzly Battle Tank，其他车辆仅具备类型门内的候选适用性。复用 Guard 的稳定 ID、实时车辆解析、归属、在场、存活、当前 Mission 与变身检查，以及 expected_native_id/expected_house/basis_frame；游戏线程允许依据帧落后至多 150 帧。Guard v1 的门和行为继续保留，Stop 版本独立查询。步兵、建筑、多车辆及目标参数不在首版支持范围内。

GameState.stop_interface_version 使用字段 18；Python NativeEvent.idle_actor 只在 event_type=6 时解析字段 7 的 whom，旧 DLL 缺失时为 None。输入匹配要求当前 actor 身份/归属仍一致、在场存活，新 Idle 的 actor RTTI=52/native ID 与请求一致，事件帧不早于发送前依据帧。按 house/timing/type/actor 排除发送前已有事件，out→do 重排帧不作为新输入；事件无请求 ID，并发人工同对象同输入仍有归因限制。

回执使用 native_input_observed，只表示观察到新输入，不要求 Mission.STOP，也不证明移动中断、队列清空或永久停车。Micro 复用 operation_observed 结算并释放租约；自动层随后可接管。未知结果保留原谓词回读，不自动重发，cancel 不发 Stop。完整 match_id/attempt_id、服务端 exactly-once 和完整动态能力查询未实现。

## 离线与构建证据

[Stop 测试](../../../tests/test_stop_interface.py)覆盖序列化、版本/身份字段、Idle 活动载荷与残留字段、旧 DLL、错误归属/类型/变身/目标数量、旧输入重排、错误 actor/house、发送前身份变化、既有 STOP/GUARD 不构成输入确认、超时未知不重发，以及正式注册表 → Commander.call → Micro → Executor 的单次结算、租约释放、延后回读和取消。初轮 Idle 对象样本为合成；本次增加 tests/data/stop_native.json 的人工 S、移动 Stop、静止 Stop 三条真实 Idle 及源录制指纹，针对本次样本与卡片改动的 236 项相关回归通过。Guard 真实样本回归继续通过。

相关回归 624 项通过，未运行无关全量测试：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_stop_interface tests.test_guard_interface tests.test_guard_tactics tests.test_native_events tests.test_proto tests.test_state tests.test_payloads tests.test_validate tests.test_intents tests.test_executor tests.test_micro tests.test_autopilot tests.test_command tests.test_mcp tests.test_replay tests.test_tactics tests.test_field_tactics
```

[构建脚本](../../../tools/build_guard_engine.py)增加 ENGINE_FEATURE=stop，使用独立 ra2yrcpp-stop 源码、ra2yrcpp-stop-i686 构建和 artifacts/stop-v1 产物；沿用已安装工具与固定依赖，不下载、不安装、不替换游戏文件。Stop 补丁相对未修改固定基线生成，包含 Guard v1，不与 Guard 补丁叠加。补丁可应用性、源码差异一致性、编译、PE32 i386、导入和 hook/导出检查通过。

```sh
ENGINE_FEATURE=stop PYTHONDONTWRITEBYTECODE=1 python3 tools/build_guard_engine.py
```

产物为 .agents/tmp/engine-build/artifacts/stop-v1/libra2yrcpp.dll，SHA-256=cf7bab758ea29152c032c83f2b3adf9b5b3d849a0bf1326c16313ea7226a5978，大小 8249061 字节，manifest.game_loaded=false。具体临时部署、备份和回滚见[Stop 部署与对照](../环境/Stop部署与对照.md)。

## 使用方审计与最小迁移

隐藏零件 halt v2 改为 ctx.call("stop")，复用正式 Stop 的策略、版本门、作用域与输入结算；requires=has_units/has_map/stop_v1，收窄为单个己方车辆，不在对战卡片中直接暴露。旧 DLL 或未知版本明确拒绝，不降级为 Hold。仓库正式技法没有调用 halt；本批用测试专用组合入口验证完整调用链，不据此声称生产组合或 DSH 已实测。

| 使用方 | 当前行为与本批决定 | 后续迁移条件 |
|---|---|---|
| halt | 已迁移为一次 Stop 输入；输入确认后释放租约，未知不重发，cancel 不发 Stop | 真机证据复用正式 stop 的 Grizzly 限定范围，其他型号与生产组合未验 |
| hold_position | 多单位旧 Hold；按既有状态谓词结算，不保证玩家 S 等价或永久驻守；保留执行路径并修正卡片 | 明确单次停止与持续位置管理需求，再决定旧名兼容和多对象部分结果 |
| hold_and_fire | 无目标发旧 Hold；有目标发 Attack，可能追击并进入接战管理；保留执行路径并修正卡片 | 明确选敌与位置约束、混合单位类型和攻击生命周期 |
| focus_fire | 无目标或远目标且 chase=false 时发旧 Hold；默认远目标发 MoveTo；保留执行路径并修正卡片 | 先补 U08 实际目标回读与追近后过早结算问题，不把停止入口替换当连续集火修复 |
| guard_area | 再次求值发现到期时发旧 Hold；接战中可能延后求值，max_frames 不是硬截止；保留执行路径并修正卡片 | 先明确持续管理、截止与租约语义，再迁移收尾动作 |
| MoveTo(hold)，含 advance_to_cell、retreat、advance_covering | 忽略目的地并发旧 STOP；保留兼容，修正推进卡片中驻守及禁火承诺 | 后续分离移动模式与停止操作，不能解释为抵达后驻守 |

本批不更改组合的选敌、攻击、移动或到期逻辑；该批没有新真机实验、DLL 替换或 DSH 重启，当时长期部署仍为 Guard、Stop 和 halt 的版本门保持关闭。该批之后的长期启用结果见[长期启用执行结果](../环境/Stop部署与对照.md#长期启用执行结果)。

新增七项行为测试覆盖 UnitPool → halt → stop 与 Commander → 测试组合 → halt → stop 的作用域、单次输入与释放；同时检查隐藏入口、旧/未知版本、地图缺失、内层 stop 被禁用、不支持对象或批量、未知输入延后回读、取消及 hold_position 双版本批量兼容。内部策略拒绝沿用 Micro 的有限等待，不记为立即成功或失败；测试随后取消释放租约。卡片说明修正后，按当前内容更新“推进”的查询预期。420 项相关测试通过，git diff --check 通过；离线测试不扩大真实 Stop 效果范围。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_stop_interface tests.test_stop_fault_transport tests.test_guard_interface tests.test_guard_tactics tests.test_tactics tests.test_tactic_actions tests.test_field_tactics tests.test_intents tests.test_executor tests.test_micro tests.test_command
```

## 未验与下一步

新 DLL 加载、Idle actor 回读、Grizzly 移动中断及静止再次输入限定通过；12 项固定请求的服务端拒绝与无输入窗口已验证，建筑及变身等动态拒绝仍未验。直接使用方审计与 halt 最小迁移已完成；hold_position 与组合中的 Hold 保留兼容路径，迁移条件见使用方审计。A1 整体仍未完成。

两侧已于 2026-10-03 按用户确认长期启用同一 Stop v1 产物，替换范围、持久备份与回滚路径见[部署记录](../环境/Stop部署与对照.md#长期启用执行结果)。随后用户授权 Agent 直接起局，只读回读两侧 guard_interface_version=1、stop_interface_version=1，MATCH 模式 stop 卡片显示而 halt 隐藏，新 DLL 已确认在对局中加载；证据与范围见[运行加载检查（已通过）](../环境/Stop部署与对照.md#运行加载检查已通过)。该检查不覆盖完整 DSH 生命周期。

持续暂停恢复、完整 DSH idle/dispose、玩家子 Agent 冷恢复、完整联机同步、跨局身份、动态乘员、计划清空及其他型号 Stop 行为保持未验。HARV 与空 FV 对照未重新列为前置。U02 模式确认与 U08 实际目标回读仍待后续切片。

## 本次真机证据

现场目录 .agents/tmp/a1-stop/ 保存 report.json、两侧逐帧录制、recording-evidence.json、两次正式技法决策与结果。对象为 Alpha 的 Grizzly Battle Tank，native_id=1043823；Beta 对应对象由初始位置 (38,76)、类型/健康和连续轨迹关联，仅作诊断，不向 L1 提供敌方隐藏信息。测试没有自动技法或 DSH 游戏工具参与，模型动作只经 stop 技法。

| 场景 | 输入与效果 | 结论 |
|---|---|---|
| 人工 S | 2401 帧开始前往 (54,76)，2463 帧录到 Idle/actor=1043823；2488 帧在 (45,76) 回 GUARD | 到达前中断移动；用户确认人工按键 |
| 正式 stop 移动对照 | 5821 帧 MOVE，目标 (65,80)；5823 帧提交一次，5825 帧录到 Idle，5826 帧 native_input_observed/operation_observed 结算；5873 帧在 (47,77) 回 GUARD | 输入早于停车；用户确认刚起步即停止；窗口 5790–6370 仅一次该 actor Idle |
| 静止再次 stop | 8572 帧原为 GUARD；8574 帧录到不同 timing 的 Idle，8575 帧输入结算；8550–9120 保持 (47,77)/GUARD | 旧 GUARD 不冒充新输入；窗口内仅一次 Idle，无重复提交 |

三个窗口两侧位置/Mission 转换帧逐项相同，属于本次对象与短窗口的一致性证据，不是完整联机同步验收。两次技法各只有一条 command_sent，任务释放租约且无后续重发。停止后 destination 仍保留原目标，说明旧 destination 不代表仍在执行移动；输入 is_executed 元数据也不替代实际效果。

原始录制与三条提取样本的来源指纹见 tests/data/stop_native.json。新增真实样本测试初次因错误沿用合成对象 native_id 失败，修正为样本 ID 后 236 项相关回归通过；没有修改产品谓词迎合样本。停止不是即时固定坐标、永久禁火或计划清空；不推广至 CMIN/FV、步兵或其他状态。

## 服务端拒绝补测结果

测试专用 [StopFaultTransport](../../../tests/stop_fault_transport.py) 在正式 stop 技法、作用域和 L0 校验之后，只对一次 UnitOrder.PLAYER_STOP 载荷注入固定错误；不增加模型工具或任意 action，不修改生产校验。两个独立运行均以合法 Stop 正例夹住拒绝场景，正例确认新 Idle 后按 operation_observed 结算；非法请求均收到 code=1 的明确服务端拒绝，任务 failed、unverified=0、无成功回执、租约释放，每项每次运行恰好一次发送。

| 固定错误 | 实际服务端拒绝 | 证据范围 |
|---|---|---|
| wrong_native_id | controlled actor absent, changed or unsupported | 首轮完整窗口 |
| wrong_house | controlled player context changed | 首轮完整窗口 |
| stale_basis / future_basis | controlled basis frame is stale | 首轮完整窗口；stale 使用 0，future 为当前依据帧 +100000，不证明 150/151 精确边界 |
| empty_actors / multiple_actors | controlled order requires one actor, native ID and house | 首轮完整窗口；multiple 重复同一车辆，不证明混合单位批量语义 |
| missing_native_id / missing_house | controlled order requires one actor, native ID and house | 首轮完整窗口 |
| coordinates / object_target | stop does not accept a target | 首轮完整窗口；coordinates 是显式存在的空消息 |
| foreign_actor / infantry_actor | controlled actor absent, changed or unsupported | 首轮拒绝回执通过；尾段补跑取得完整窗口 |

首轮目录 .agents/tmp/a1-stop-rejections/ 保存 12 项回执、两次正例、轮询状态与逐帧录制。原始 gzip 快照及游戏关闭后录制均止于 1063 帧：前 10 项窗口完整；foreign_actor 为 1035–1063 的部分窗口，infantry_actor 与最后正例未落盘。没有将截断尾段记为逐帧通过。仅补跑两项及前后正例，目录 .agents/tmp/a1-stop-rejections-tail/；脚本只读等待两侧录制已落盘至末尾正例窗口之后再结束，无额外操作请求。

尾段 foreign_actor 的 389–435 帧、infantry_actor 的 456–501 帧完整；对应首轮前 10 项完整窗口合计覆盖全部 12 项，每个窗口至少 45 个推进帧，记录逐帧连续。三个夹具（己方 Grizzly、己方 GI、外方 Grizzly）在 Alpha 的原始状态中位置、健康、Mission 与 native ID 保持不变，全部窗口没有新 Idle；外方 ID 仅由 Beta 己方观测与初始类型/位置配对取得，用于拒绝夹具诊断。完整联机同步未验。

两轮 gzip 都没有完整文件尾，已落盘的测试窗口完整；仅解析完整消息，保留尾部截断限制。recording-check.json 记录实际覆盖、来源哈希与 Idle。尾段补测原始录制只出现两个正例的对应 Idle。原版事件无请求 ID，本次独占写入与固定夹具可关联证据，不承诺 exactly-once 或无限期无异常。

[真实回执样本](../../../tests/data/stop_rejections_native.json)保存首轮 12 条请求/回执、源报告及逐项完整窗口的录制指纹，尾段项指向第二轮。失败 payload 是请求回声；[测试](../../../tests/test_stop_fault_transport.py)验证固定故障复现、重复 actor/默认字段的回声语义，并将真实失败回执送过 Executor，确认不读取回声为状态、不等待生效、不重试。新增样本后相关 234 项回归通过，未重复无关全量测试。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_stop_fault_transport tests.test_stop_interface tests.test_guard_fault_transport tests.test_executor tests.test_micro tests.test_command
```

建筑对象及变身期间拒绝仍未执行：默认开局没有建筑，变身状态须隔离至游戏线程检查时点；其余死亡、limbo、在场失效、150/151 帧边界和多种异构 actor 也未专门实测。保留既有离线检查与源码依据，不将本批 12 项推广为全部动态安全条件。环境与回滚结果见[Stop 部署与对照](../环境/Stop部署与对照.md#拒绝补测执行与恢复)。
