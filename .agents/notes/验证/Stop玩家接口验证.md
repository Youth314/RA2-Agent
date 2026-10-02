# Stop 玩家接口验证

日期：2026-10-02。状态：A0 已完成 34 项覆盖矩阵与首组契约；A1 首个 Stop 切片已实现、离线回归和独立 DLL 构建通过，已完成临时部署及 Grizzly 三项限定真机对照，测试后恢复 Guard DLL。计划与契约见[建设计划](../设计/玩家操作接口建设计划.md)和[接口审计](../../drafts/接口/L1基础接口契约与现状审计.md#a0-玩家能力覆盖矩阵)。

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

## 未验与下一步

新 DLL 加载、Idle actor 回读、Grizzly 移动中断及静止再次输入限定通过；服务端拒绝场景尚未专门真机验证。当前未迁移 hold_position、halt、guard_area 或 focus_fire，A1 整体仍未完成。

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

## 服务端拒绝补测准备

测试专用 tests/stop_fault_transport.py 在正式 stop 技法、作用域和 L0 校验之后，只对一次 UnitOrder.PLAYER_STOP 载荷注入固定错误；不增加模型可调用工具，不修改生产校验，不接受任意 action。12 项为 wrong_native_id、wrong_house、stale_basis、future_basis、empty_actors、multiple_actors、missing_native_id、missing_house、coordinates、object_target、foreign_actor、infantry_actor。预期服务端错误文本按当前 Stop 固定补丁逐分支定义，当前尚无本批真实拒绝回执。

对应离线测试覆盖固定字段差异、错误基线/夹具拒绝、每种合成拒绝回执只发送一次且不解析回声、故障单次消费及传输未知不重试。相关 232 项回归通过（test_stop_fault_transport、test_stop_interface、test_guard_fault_transport、test_executor、test_micro、test_command）。合成拒绝回执不是 DLL 实测证明。

本批脚本在 .agents/tmp/a1-stop-rejections/；run.py 复用已有启动/配置备份恢复流程，probe.py 经正式 stop 注册表、Commander/Micro 和测试传输层运行，两次合法正例夹住 12 个非法请求；每例要求明确服务端拒绝、任务失败且非 unverified、释放租约、恰好一次发送，随后至少 45 个推进帧内对象状态不变且无新 Idle。两侧逐帧录制另行复核以弥补轮询漏采；当前脚本仅语法检查，真机执行待本次临时部署确认。

建筑对象及变身期间拒绝仍未执行：默认开局没有建筑，变身状态需隔离至实际游戏线程检查时点；不通过改内存或合成状态冒充真机结果。其余在场/死亡/limbo 等动态边界也不由这 12 项自动覆盖；是否准备场景按具体证据成本决定。
