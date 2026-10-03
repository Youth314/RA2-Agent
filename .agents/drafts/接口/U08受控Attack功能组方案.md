# U08 受控 Attack 功能组

更新日期：2026-10-03。状态：用户已确认协议、Python、DLL 源码及项目内离线构建；功能组已实现，必要离线检查通过，独立构建及 PE 检查通过，未部署或执行游戏动作。用户已确认[功能组验证节奏](../../notes/验证/能力验证方法.md#1-验证目标与投入)，本组合并请求、必要身份、观测判据和薄技法，完成后集中验证。既有 Target 回读与真机证据复用[U08 验证](../../notes/验证/U08实际目标回读验证.md)。实现事实与产物集中维护在[Attack 功能组验证](../../notes/验证/Attack玩家接口验证.md)；部署与游戏动作另按批确认。

## 1. 首版范围与复用

新意图 AttackTarget(units=(单个己方车辆 Agent ID,), target=合法敌方 Agent ID)，一次普通指定攻击；薄技法 attack_target，匹配输入与当前目标后释放租约，不承诺击毁、永久接战或禁火。模型不传指针、native ID、任意 Mission 或事件。目标首版为存活、在场、非 limbo 的普通敌方车辆或建筑；己方、盟友、中立、隐形/伪装、FogOfWar=Yes、Cell/ForceFire、飞机/步兵目标和批量 actor 保留 unsupported。车辆效果真机声明先限 MTNK，其他型号不因通用 actor 解析可用而记通过。

复用 Stop/Guard 的游戏线程单车辆解析、玩家/身份/依据帧/变身检查，复用 Target 的同帧 Techno 成员索引、RTTI/WhatAmI 和保守可见性门。现有 Attack → action=8 保留为旧路径，不宣称获得新契约；focus_fire/guard_area 不在首版批量迁移。新薄技法必须使用新能力门，缺能力明确 unsupported，不回退旧 Attack/Mission.ATTACK；Target v1 只读兼容继续保留。

## 2. 已查明的缺口

现有 Executor._plan_attack 只按指针判断目标存在，verify 只看 Mission.ATTACK；旧 UnitOrderCtx::click_mission 会在无坐标时从 ctx_->get_object_entry(target) 的状态缓存取目标位置。新分支直接解析游戏线程当前成员并构造对象 Target，不依赖该缓存取敌方坐标，不同时附带 Cell/Destination。输入路径拟复用固定 abi::ClickMission(Mission::Attack, checked_target, nullptr, nullptr)，其返回值、事件和后续状态分别处理，不能将一次 bool 或编译成功当作效果。

仅增加 expected_target_native_id 而不提供合法目标身份不够：现有外方 Object.native_id=21 不导出，L1 不能从 Alpha 私有状态或 actor 旧 Target 补齐 Beta 的新请求。新增最少的内部目标身份字段，DLL 只给通过本组合法性门的目标；Observer 清除所有公开 GameObject 中的原始命令身份，模型只见 Agent ID。该字段不改变原 native_id=21 的己方限定语义。

IdentityTable 的变身启发式可能延续 Agent ID。L0 必须先保存意图依据帧的 actor/target 绑定，再读新帧并核对指针、native ID、归属与具体类型；不能用已重映射的 Agent ID 为旧请求生成新的期望身份。DLL 再按实际执行时的当前成员复查，地址未知时不解引用，身份改变时拒绝而非追随新对象。

## 3. 协议与原生门

| 位置 | 新增字段 | 用途与兼容 |
|---|---|---|
| UnitAction | PLAYER_ATTACK_TARGET=16 | 独立受控分支，不改变旧 ATTACK=8 或 Guard/Stop=13–15 |
| GameState | attack_interface_version=20 | v1 明确同时提供请求与合法目标命令身份；Target 版本 19 保持原义 |
| Object | optional uint32 order_target_native_id=23 | 只对本组合法敌方目标导出 UniqueID；内部绑定，公开 Observation/工具不携带，旧字段 21/22 不变 |
| UnitOrder | expected_target_native_id=8、expected_target_house=9、expected_target_type=10 | 与 target_object=3 共同绑定依据帧目标；缺失/零/类型不支持时拒绝 |
| UnitOrder 已有扩展 | expected_native_id=5、expected_house=6、basis_frame=7 | 沿用 actor/玩家/时效门；仓库 commands_game.proto 已同步 DLL 原有字段，不重复占号 |

字段号已对照完整 Target 协议补丁与仓库 schema，并经本组 protoc 编码检查通过。合法目标身份不授予全量敌方身份读取：未满足 live/on-map/non-limbo、类型、未 shrouded、无 cloak/disguise、三个 FogOfWar 关闭和敌我关系门时字段缺失；未知上下文也缺失。HouseClass::IsAlliedWith(HouseClass const*) 的固定声明地址为 0x4F9A50；已核对锁定 ABI 包装与 owner/House/HouseType 成员来源，盟友、中立或无法判定关系不支持，不能用 Owner != CurrentPlayer 代替敌对关系。新增原生读取和调用应有固定布局/ABI 约束，不假定 MinGW 的虚调用可用。

HouseClass::Type=0x34 与 HouseTypeClass::MultiplayPassive=0x1A6 的锁定 i686 布局已通过编译断言。游戏线程执行顺序：复用 controlled_vehicle → 按指针值查当前目标成员 → 核对期望 UniqueID/Owner/WhatAmI → 检查目标可见性与敌对关系 → 构造原版对象 Target → 单次 ClickMission。目标移动不改变身份且可继续使用；消失、变身、归属/类型/身份改变或当前合法性不足时明确拒绝。首版 basis_frame 时效沿用现有 150 帧，不增加跨局、服务器去重或完整请求 ID 的支持声明。

## 4. 观测与任务结算

输入线索要求新 MegaMission 条目与本次 actor、Mission_Attack 和目标 RTTI=52/UniqueID 匹配，排除依据帧已有条目。事件没有请求 ID，只有在单写入者和本次采样窗口内作限定关联；队列中的事件、is_executed 标签及未来事件帧不单独证明游戏已经执行。

Target 匹配独立读取当帧合法 Observation.actual_targets，同时由内部绑定核对 actor/target 的实际 native ID、类型和归属。NONE、UNOBSERVABLE、未提供、对象缺席、宽限期旧身份或另一目标均不能匹配。下令前已经同目标则记 preexisting_match；Target 由别的值变成所请求目标才记 state_changed，均不冒充开火或击毁。

薄技法的成功条件为本次新输入线索与合法当前目标均已取得；分别保留两项证据，operation_observed 不表示效果完成。超时/传输中断后结果未知，保留待回读计划、不自动再发；输入已观察而 Target 未确认时也不记成功。cancel 只释放任务与租约，不发送 Stop。开火、健康变化或目标消失单独记录，消失不自动解释为死亡。

## 5. 改动、构建与验证批次

| 范围 | 拟实施位置 |
|---|---|
| 协议与完整补丁 | proto/ra2yrproto/{ra2yr,commands_game}.proto；engine/ra2yrcpp/patches/attack-v1-{engine,protocol}.patch，包含已验 Target/Stop/Guard，相对同一固定基线生成，不叠加旧补丁 |
| 原生分支与合法身份 | 独立源码中的 commands_game.cpp、state_parser.cpp、hooks_yr.cpp、abi 包装和最少策略头；不修改旧输入分支的语义 |
| Python 链路 | engine/{state,observation,identity,payloads,client,validate}.py、constants.py、runtime/{intents,executor,micro}.py；只改新请求和必要身份/结算分支 |
| 薄技法 | 新 attack_target 与能力筛选，按 ra2-write-tactic 规范离线检查；不公开 raw API，不默认迁移旧组合 |
| 构建 | tools/build_guard_engine.py 增加 attack 选项；独立 .agents/tmp/engine-build/{sources/ra2yrcpp-attack,build/ra2yrcpp-attack-i686,artifacts/attack-v1}，复用缓存，不安装/下载，不覆盖旧产物 |

离线只覆盖本组新增 schema/缺能力、新目标身份和合法性、两项判据/未知不重发、薄技法作用域与一次结算四类问题；拒绝条件用表驱动样本，不为每个条件单建环境。改动完成后运行一次受影响的相关测试类；既有 Target wire/原生策略只有实际改动才重跑，不重复全部 state/identity/native_events/proto/Guard/Stop 套件。构建完成执行一次必要的补丁、PE/导出/指纹检查，失败修复后只补受影响步骤。

真机另获整批范围授权后，一次临时部署并复用同一局：单 MTNK 对 AMCV 的受控输入/目标匹配；人工在健康门成立且目标仍非空时及时展开；如需证明服务端身份复查，仅注入一个固定的目标 ID 不匹配条件；随后单次对新合法 GACNST 请求，取得建筑 Target/必要效果。每个新目标输入各一次，单窗口的已匹配状态不触发重发；预先约定人工展开时机，避免采到非空后长时间等待回复造成失血。已有加载/空 Target/Stop 对照只复用，未知及未验范围保留，不再另起局补齐全矩阵。

本组源码与离线构建已获确认；本页不申请安装、改配置或起局。部署时保存当时实际 Stop v1 持久备份、双侧硬链接和配置指纹；本批结束仅关闭本轮 PID并恢复 Stop v1，旧 installed 清单保持原状态。实现和编译均不能自动升级为已测或长期启用。
