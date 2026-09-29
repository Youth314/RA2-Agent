# 副官事件的中文名、分类与可见性

`codex/eva.md` 的两列（可见性、可合成）与中文名、分类都来自本文件。**一行一条**：

```
事件名 | 分类 | 中文名 | 可见性 | 可合成
```

`可见性`：`己方` / `全图` / `需渗透`。`可合成`：`可` / `推断` / `不可`。

**触发条件不在 `evamd.ini` 里**（那是引擎代码），所以可见性一列是人填的初稿，
按名字推断而来，**需要真机核对**。引擎只告诉我们有哪些事件、它自己给的分级与原文。

## 那 17 个「全图」事件，我们合成不了

引擎无条件向所有人播报，而我们的观测按迷雾过滤——所以「侦测到敌方核弹井」这种事，
我们既看不到那个建筑，也不该去读敌方的内部状态。同理，**全部出厂报告也拿不到**。

<!-- 分类：超级武器 / 被渗透与破坏 / 经济与电力 / 损失与受袭 / 生产与建造 / 升级 /
     地盘控制 / 联盟与外交 / 指令反馈 / 侦察与投送 / 战役专用 -->

EVA_NuclearSiloDetected | 超级武器 | 侦测到核弹发射井 | 全图 | 不可
EVA_NuclearMissileReady | 超级武器 | 核弹就绪 | 己方 | 可
EVA_NuclearMissileLaunched | 超级武器 | 核弹已发射 | 全图 | 不可
EVA_IronCurtainDetected | 超级武器 | 侦测到铁幕 | 全图 | 不可
EVA_IronCurtainReady | 超级武器 | 铁幕就绪 | 己方 | 可
EVA_IronCurtainActivated | 超级武器 | 铁幕已激活 | 全图 | 不可
EVA_ChronosphereDetected | 超级武器 | 侦测到超时空传送仪 | 全图 | 不可
EVA_ChronosphereReady | 超级武器 | 超时空传送仪就绪 | 己方 | 可
EVA_ChronosphereActivated | 超级武器 | 超时空传送仪已激活 | 全图 | 不可
EVA_WeatherDeviceReady | 超级武器 | 侦测到天气控制器 | 己方 | 可
EVA_LightningStormReady | 超级武器 | 闪电风暴就绪 | 己方 | 可
EVA_LightningStormCreated | 超级武器 | 闪电风暴已生成 | 全图 | 不可
EVA_PsychicDominatorDetected | 超级武器 | 侦测到心灵控制器 | 全图 | 不可
EVA_PsychicDominatorReady | 超级武器 | 心灵控制器就绪 | 己方 | 可
EVA_PsychicDominatorActivated | 超级武器 | 心灵控制器已激活 | 全图 | 不可
EVA_GeneticMutatorDetected | 超级武器 | 侦测到基因突变器 | 全图 | 不可
EVA_GeneticMutatorReady | 超级武器 | 基因突变器就绪 | 己方 | 可
EVA_GeneticMutatorActivated | 超级武器 | 基因突变器已激活 | 全图 | 不可
EVA_ForceShieldReady | 超级武器 | 力场护盾就绪 | 己方 | 可
EVA_ForceShieldActivated | 超级武器 | 力场护盾已激活 | 全图 | 不可
EVA_PsychicRevealReady | 超级武器 | 心灵震荡就绪 | 己方 | 可
EVA_BuildingInfiltrated | 被渗透与破坏 | 建筑被渗透 | 己方 | 可
EVA_BuildingInfTechStolen | 被渗透与破坏 | 被渗透：科技被窃 | 己方 | 可
EVA_BuildingInfRadarSabotaged | 被渗透与破坏 | 被渗透：雷达被破坏 | 己方 | 可
EVA_BuildingInfCashStolen | 被渗透与破坏 | 被渗透：资金被窃 | 己方 | 可
EVA_BuildingInfiltratedPowerSabotaged | 被渗透与破坏 | 被渗透：电力被破坏 | 己方 | 可
EVA_TechnologyStolen | 被渗透与破坏 | 科技被窃 | 己方 | 可
EVA_RadarSabotaged | 被渗透与破坏 | 雷达被破坏 | 己方 | 可
EVA_CashStolen | 被渗透与破坏 | 资金被窃 | 己方 | 可
EVA_PowerSabotaged | 被渗透与破坏 | 电力被破坏 | 己方 | 可
EVA_FirePowerTechStolen | 被渗透与破坏 | 火力科技被窃（我方升级） | 己方 | 可
EVA_ArmorTechStolen | 被渗透与破坏 | 装甲科技被窃（我方升级） | 己方 | 可
EVA_InsufficientFunds | 经济与电力 | 资金不足 | 己方 | 可
EVA_LowPower | 经济与电力 | 电力不足 | 己方 | 可
EVA_EnemyBasePoweredDown | 经济与电力 | 敌方基地断电 | 需渗透 | 推断
EVA_EnemyPowerRestored | 经济与电力 | 敌方电力恢复 | 需渗透 | 推断
EVA_OreMinerUnderAttack | 经济与电力 | 矿车被攻击 | 己方 | 可
EVA_OreMinerOffLine | 经济与电力 | 矿车离线 | 己方 | 可
EVA_ChronoMinerOffline | 经济与电力 | 超时空矿车离线 | 己方 | 可
EVA_UnitLost | 损失与受袭 | 单位阵亡 | 己方 | 可
EVA_CriticalUnitLost | 损失与受袭 | 关键单位阵亡 | 己方 | 可
EVA_CriticalStrucureLost | 损失与受袭 | 关键建筑被毁 | 己方 | 可
EVA_OurBaseIsUnderAttack | 损失与受袭 | 基地被攻击 | 己方 | 可
EVA_OurAllyIsUnderAttack | 损失与受袭 | 盟友被攻击 | 己方 | 可
EVA_TechBuildingLost | 损失与受袭 | 科技建筑丢失 | 己方 | 可
EVA_BuildingOffLine | 损失与受袭 | 建筑离线 | 己方 | 可
EVA_BuildingOnLine | 损失与受袭 | 建筑上线 | 己方 | 可
EVA_BaseDefensesOffLine | 损失与受袭 | 防御设施离线 | 己方 | 可
EVA_RobotTanksOffline | 损失与受袭 | 遥控坦克离线 | 己方 | 可
EVA_RobotTanksBackOnline | 损失与受袭 | 遥控坦克恢复 | 己方 | 可
EVA_WeatherControlOffline | 损失与受袭 | 天气控制器离线 | 己方 | 可
EVA_WeatherControlUnavailable | 损失与受袭 | 天气控制器不可用 | 己方 | 可
EVA_ConstructionComplete | 生产与建造 | 建造完成 | 己方 | 可
EVA_UnitReady | 生产与建造 | 单位就绪 | 己方 | 可
EVA_Building | 生产与建造 | 开始建造 | 己方 | 可
EVA_Training | 生产与建造 | 训练中 | 己方 | 可
EVA_NewConstructionOptions | 生产与建造 | 有新建筑可造 | 己方 | 可
EVA_NewTechnologyAcquired | 生产与建造 | 获得新科技 | 己方 | 可
EVA_UpgradeInProgress | 生产与建造 | 升级进行中 | 己方 | 可
EVA_UpgradeComplete | 生产与建造 | 升级完成 | 己方 | 可
EVA_UnitPromoted | 升级 | 单位晋升 | 己方 | 可
EVA_UnitUpgraded | 升级 | 单位升级 | 己方 | 可
EVA_UnitFirePowerUpgraded | 升级 | 单位火力升级 | 己方 | 可
EVA_UnitArmorUpgraded | 升级 | 单位装甲升级 | 己方 | 可
EVA_UnitSpeedUpgraded | 升级 | 单位速度升级 | 己方 | 可
EVA_FirepowerUpgraded | 升级 | 全军火力升级 | 己方 | 可
EVA_ArmorUpgraded | 升级 | 全军装甲升级 | 己方 | 可
EVA_SpeedUpgraded | 升级 | 全军速度升级 | 己方 | 可
EVA_BuildingCaptured | 地盘控制 | 占领建筑 | 己方 | 可
EVA_TechBuildingCaptured | 地盘控制 | 占领科技建筑 | 己方 | 可
EVA_OilRefineryCaptured | 地盘控制 | 占领油井 | 己方 | 可
EVA_HospitalCaptured | 地盘控制 | 占领医院 | 己方 | 可
EVA_MachineShopCaptured | 地盘控制 | 占领机器商店 | 己方 | 可
EVA_AirfieldCaptured | 地盘控制 | 占领机场 | 己方 | 可
EVA_SecretLabCaptured | 地盘控制 | 占领秘密实验室 | 己方 | 可
EVA_RepairFacilityCaptured | 地盘控制 | 占领维修厂 | 己方 | 可
EVA_StructureGarrisoned | 地盘控制 | 建筑被进驻 | 己方 | 可
EVA_StructureAbandoned | 地盘控制 | 建筑被放弃 | 己方 | 可
EVA_StructureSold | 地盘控制 | 建筑被变卖 | 己方 | 可
EVA_StructureRepaired | 地盘控制 | 建筑被修复 | 己方 | 可
EVA_UnitSold | 地盘控制 | 单位被变卖 | 己方 | 可
EVA_UnitRepaired | 地盘控制 | 单位被修复 | 己方 | 可
EVA_Repairing | 地盘控制 | 修复中 | 己方 | 可
EVA_AllianceFormed | 联盟与外交 | 结盟达成 | 己方 | 可
EVA_AllianceBroken | 联盟与外交 | 联盟破裂 | 己方 | 可
EVA_AllianceRequested | 联盟与外交 | 收到结盟请求 | 己方 | 可
EVA_RequestingAlliance | 联盟与外交 | 正在请求结盟 | 己方 | 可
EVA_EnemyAllianceFormed | 联盟与外交 | 敌方结盟 | 需渗透 | 推断
EVA_PlayerResigned | 联盟与外交 | 有玩家投降 | 己方 | 可
EVA_PlayerDefeated | 联盟与外交 | 有玩家被击败 | 己方 | 可
EVA_UnableToComply | 指令反馈 | 无法执行 | 己方 | 可
EVA_Canceled | 指令反馈 | 已取消 | 己方 | 可
EVA_OnHold | 指令反馈 | 已暂停 | 己方 | 可
EVA_SelectTarget | 指令反馈 | 请选择目标 | 己方 | 可
EVA_PrimaryBuildingSelected | 指令反馈 | 已设为主建筑 | 己方 | 可
EVA_NewRallyPointEstablished | 指令反馈 | 新集结点已设 | 己方 | 可
EVA_CannotDeployHere | 指令反馈 | 此处无法展开 | 己方 | 可
EVA_SpyPlaneEnRoute | 侦察与投送 | 间谍机在途 | 己方 | 可
EVA_SpyPlaneReady | 侦察与投送 | 间谍机就绪 | 己方 | 可
EVA_ParatroopersReady | 侦察与投送 | 伞兵就绪 | 己方 | 可
EVA_AirstrikeInitiated | 侦察与投送 | 空袭已发起 | 己方 | 可
EVA_ReinforcementsReady | 侦察与投送 | 增援就绪 | 己方 | 可
EVA_ReinforcementsHaveArrived | 侦察与投送 | 增援到达 | 己方 | 可
EVA_BeaconPlaced | 侦察与投送 | 已放置信标 | 己方 | 可
EVA_BeaconDetected | 侦察与投送 | 侦测到信标 | 全图 | 不可
EVA_EnemyAirArmadaDetected | 侦察与投送 | 侦测到敌方空军编队 | 全图 | 不可
EVA_EnemyFleetDetected | 侦察与投送 | 侦测到敌方舰队 | 全图 | 不可
EVA_ArmorBattallianDetected | 侦察与投送 | 侦测到敌方装甲营 | 全图 | 不可
EVA_EnemyInfantryBattalionDetected | 侦察与投送 | 侦测到敌方步兵营 | 全图 | 不可
EVA_MissionAccomplished | 战役专用 | 任务完成 | 己方 | 可
EVA_MissionFailed | 战役专用 | 任务失败 | 己方 | 可
EVA_BattleControlTerminated | 战役专用 | 战斗控制终止 | 己方 | 可
EVA_EstablishBattlefieldControl | 战役专用 | 建立战场控制 | 己方 | 可
EVA_BattleControlOnline | 战役专用 | 战斗控制上线 | 己方 | 可
EVA_BattlefieldControlOnline | 战役专用 | 战场控制上线 | 己方 | 可
EVA_PrimaryObjectiveAchieved | 战役专用 | 主目标达成 | 己方 | 可
EVA_SecondaryObjectiveAchieved | 战役专用 | 次目标达成 | 己方 | 可
EVA_TertiaryObjectiveAchieved | 战役专用 | 第三目标达成 | 己方 | 可
EVA_ObjectiveComplete | 战役专用 | 目标完成 | 己方 | 可
EVA_NewMissionObjective | 战役专用 | 新任务目标 | 己方 | 可
EVA_NewObjectiveReceived | 战役专用 | 收到新目标 | 己方 | 可
EVA_YouAreVictorious | 战役专用 | 你胜利了 | 己方 | 可
EVA_YouHaveLost | 战役专用 | 你失败了 | 己方 | 可
EVA_YouHaveResigned | 战役专用 | 你已投降 | 己方 | 可
EVA_TimerStarted | 战役专用 | 计时开始 | 己方 | 可
EVA_TimerStopped | 战役专用 | 计时停止 | 己方 | 可
EVA_20MinutesRemaining | 战役专用 | 剩余 20 分钟 | 己方 | 可
EVA_10MinutesRemaining | 战役专用 | 剩余 10 分钟 | 己方 | 可
EVA_5MinutesRemaining | 战役专用 | 剩余 5 分钟 | 己方 | 可
EVA_4MinutesRemaining | 战役专用 | 剩余 4 分钟 | 己方 | 可
EVA_3MinutesRemaining | 战役专用 | 剩余 3 分钟 | 己方 | 可
EVA_2MinutesRemaining | 战役专用 | 剩余 2 分钟 | 己方 | 可
EVA_1MinuteRemaining | 战役专用 | 剩余 1 分钟 | 己方 | 可
EVA_IncomingTransmission | 战役专用 | 收到通讯 | 己方 | 可
EVA_NewTerrainDiscovered | 战役专用 | 发现新地形 | 己方 | 可
EVA_BridgeRepaired | 战役专用 | 桥梁修复 | 己方 | 可
