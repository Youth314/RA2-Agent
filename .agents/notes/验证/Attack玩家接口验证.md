# Attack 玩家接口验证

日期：2026-10-03。范围见[功能组方案](../../drafts/接口/U08受控Attack功能组方案.md)。用户已确认协议、Python、DLL 源码和一次项目内独立构建；本轮未获部署、配置或游戏动作授权。实现提交为 3946ba6，离线检查、独立 DLL 构建及 PE 检查通过；编译不证明玩家效果或联机同步。

## 当前契约

AttackTarget → PLAYER_ATTACK_TARGET=16，只接受一个己方在场车辆与一个合法敌方车辆/建筑。thin attack_target 使用 attack_v1/Target v1 版本门；旧 Attack/action=8、focus_fire 与 guard_area 保留兼容行为，不采用新成功声明。模型只传 Agent ID，内部目标命令身份从 Object.order_target_native_id=23 取得，GameState.attack_interface_version=20 声明 v1；UnitOrder 5–7 同步已有 actor/依据帧扩展，8–10 固定目标 native ID、house 与具体 RTTI。

下令前先固定依据帧 actor/target 的 pointer、native ID、house、RTTI 与 type_pointer，再读取新帧；Observer 更新可能延续变身 Agent ID，不能据新绑定追随新对象。DLL 在游戏线程从 Techno 当前成员查地址，复查目标身份、live/on-map/non-limbo、非变身、关系与可见性，未知地址不解引用。敌对关系使用固定 ABI 的 HouseClass::IsAlliedWith(HouseClass const*)，双方 House/HouseType 先确认数组成员，双方盟友关系或中立时拒绝。首版只在三个 FogOfWar 标志关闭、当前目标格合法且未 shrouded、非 cloak/disguise 时导出内部身份。

Observer 从所有公开 GameObject 清除 order_target_native_id 和原始 actual_target，内部身份参与 pointer reuse 检查；当前帧字段缺失不能由缓存补齐。Target 投影继续按合法可见集合与当帧身份回读；旧 DLL 明确 unsupported，无自动降级。

成功判据要求本次新 MegaMission 攻击输入与合法当前实际 Target 均匹配；依据帧已有输入不能匹配，输入与 Target 可分帧观察。回执 observations 分别保存 native_input、actual_target 及采样帧，Target 下令前已匹配记 preexisting_match，改变后匹配记 state_changed。Mission_Attack 不替代 Target；队列事件、未来事件 frame 或 is_executed 不证明游戏已执行，事件无请求 ID，关联仍受单写入者/采样窗口限制。

薄技法匹配后以 operation_observed 结算并释放租约，不表示到达、开火、击毁、长期接战或驻守。输入已见而 Target 未确认、超时或传输中断均保留待回读计划，不自动重发；cancel 只释放任务，不发送 Stop。

## 必要离线检查

执行 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_attack_target tests.test_identity tests.test_target_observation tests.test_executor.TestExecute tests.test_micro.TestCommandErrors`，81 项通过。其中本组 9 项检查合并覆盖 schema/旧 DLL 未提供、载荷与 protoc 编码、新目标身份/变身/复用/合法集合、输入与 Target 双判据/未知不重发、Commander.call 与 UnitPool/Squad 作用域、一次结算与 cancel；一项直接编译新纯 C++ 策略并表驱动核对合法性及身份变化拒绝。其余 72 项只回归实际改动影响的 identity、Target 投影和通用执行/未知结果分支。实现调试期间失败项修复后仅重跑受影响项。

不运行全量套件，不重复既有 Stop/Guard 真机对照、加载/空 Target 检查或未改动的原版事件解析与旧原生 Target 策略。新游戏行为仍待集中真机验证。

## 独立构建

源码、build、artifact 分别位于 .agents/tmp/engine-build/sources/ra2yrcpp-attack、build/ra2yrcpp-attack-i686、artifacts/attack-v1。完整 attack-v1-engine/protocol.patch 相对同一固定干净基线生成，包含 Target/Stop/Guard，不叠加旧补丁；复用缓存依赖，无安装或下载。

第一次编译在新增 HouseClass::Type 布局断言处发现预期偏移错误；锁定 YRpp/MinGW i686 的编译值为 0x34，已修正并保留 attack-build-attempt1.log。续编使用 ENGINE_RESUME_BUILD=1，核对配置缓存的 source/version 后复用已完成配置与 object，不重跑 Python 检查。HouseTypeClass::MultiplayPassive 预期 0x1A6 的断言保留，既有 Target 布局断言继续生效。续编完成，产物 libra2yrcpp.dll 为 8270734 字节，SHA-256=da532b09121551e841036b15dd758b401be5dd6bc8259528bc3f0e84ab4758cb；PE32 Intel i386 DLL、四个既有 Windows runtime imports、7 个导出、.syhks00 hook 段和单一版本资源检查通过。完整指纹与依赖记录位于 .agents/tmp/engine-build/artifacts/attack-v1/manifest.json，game_loaded=false；命令和构建日志位于 .agents/tmp/engine-build/logs/attack-*.log。引擎补丁 SHA-256=46e2e60b52e165a47cfd91ea85a68a6b7dbb82d0ed262812feabadd0a11fe5a6，协议补丁 SHA-256=b9516ed1c58c54d6b0be9e188fe01aa69b3b2bd7304a43bd05abdbf8dd8e9754。

## 真机范围与剩余边界

Attack v1 产物未部署或加载，MTNK → AMCV / GACNST 受控请求、原生服务端目标 ID 不匹配拒绝、非空目标中的及时展开均未验。既有人工 MTNK → AMCV 非空 Target 证据只在[U08 验证](U08实际目标回读验证.md)维护，不证明新 DLL 请求可靠。操作批次见[集中真机操作单](../../drafts/接口/Attack集中真机操作单.md)，需单独确认部署和游戏动作范围。

其他型号与武器、步兵/飞机目标、盟友/中立目标、FogOfWar=Yes、Cell/ForceFire、请求去重、跨局身份、完整 DSH 生命周期及完整联机同步不属于已验证支持。长期游戏 DLL 基线仍为 Stop v1，具体环境事实见[Stop 部署](../环境/Stop部署与对照.md)。
