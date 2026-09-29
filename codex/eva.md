# 副官事件

由 `corpus/raw/evamd.ini` 生成，不要手改。**中文名、可见性与可合成三列来自人写的 `corpus/notes/eva_annotations.md`**，其余都是引擎原文。

共 136 个 `EVA_*` 事件、87 条 `Unit_*_<Type>` 单位出厂报告。

两套机制：`EVA_*` 是全局警告；`Unit_*_<Type>` 是「某单位出厂了」，单位与建筑都有，两套副官（Eva 与 Sofia）只有语音不同，故合并成一条。这类报告引擎无条件全图播报，**我们拿不到**——观测按迷雾过滤。

`优先级` 与 `排队` 是引擎自己的取值——拿它决定哪些事件值得叫醒模型，不必另立一套。

## 事件

| 中文名 | 事件 | 引擎原文 | 优先级 | 排队 | 可见性 | 可合成 |
|---|---|---|---|---|---|---|
| 战斗控制终止 | `EVA_BattleControlTerminated` | Battle control terminated. | CRITICAL |  | 己方 | 可 |
| 战场控制上线 | `EVA_BattlefieldControlOnline` | BattlefieldControlOnline | CRITICAL |  | 己方 | 可 |
| 超时空传送仪已激活 | `EVA_ChronosphereActivated` | Warning:  Chronosphere activated. | CRITICAL |  | 全图 | 不可 |
| 侦测到超时空传送仪 | `EVA_ChronosphereDetected` | Warning:  Chronosphere detected. | CRITICAL | 是 | 全图 | 不可 |
| 建立战场控制 | `EVA_EstablishBattlefieldControl` | Establishing battlefield control…standby. | CRITICAL |  | 己方 | 可 |
| 铁幕已激活 | `EVA_IronCurtainActivated` | Warning:  Iron Curtain activated. | CRITICAL |  | 全图 | 不可 |
| 侦测到铁幕 | `EVA_IronCurtainDetected` | Warning:  Iron Curtain detected. | CRITICAL | 是 | 全图 | 不可 |
| 闪电风暴已生成 | `EVA_LightningStormCreated` | Warning:  Lightning Storm created. | CRITICAL |  | 全图 | 不可 |
| 核弹已发射 | `EVA_NuclearMissileLaunched` | Warning:  Nuclear Missile Launched. | CRITICAL |  | 全图 | 不可 |
| 联盟破裂 | `EVA_AllianceBroken` | Alliance broken. | IMPORTANT | 是 | 己方 | 可 |
| 结盟达成 | `EVA_AllianceFormed` | Alliance formed. | IMPORTANT | 是 | 己方 | 可 |
| 资金被窃 | `EVA_CashStolen` | Cash stolen. | IMPORTANT | 是 | 己方 | 可 |
| 敌方结盟 | `EVA_EnemyAllianceFormed` | Enemy alliance formed. | IMPORTANT | 是 | 需渗透 | 推断 |
| 电力不足 | `EVA_LowPower` | Low power. | IMPORTANT | 是 | 己方 | 可 |
| 发现新地形 | `EVA_NewTerrainDiscovered` | New terrain discovered. | IMPORTANT | 是 | 己方 | 可 |
| 侦测到核弹发射井 | `EVA_NuclearSiloDetected` | Warning:  Nuclear Silo detected. | IMPORTANT | 是 | 全图 | 不可 |
| 有玩家被击败 | `EVA_PlayerDefeated` | Player defeated. | IMPORTANT | 是 | 己方 | 可 |
| 有玩家投降 | `EVA_PlayerResigned` | Player resigned. | IMPORTANT | 是 | 己方 | 可 |
| 电力被破坏 | `EVA_PowerSabotaged` | Power sabotaged. | IMPORTANT |  | 己方 | 可 |
| 雷达被破坏 | `EVA_RadarSabotaged` | Radar sabotaged. | IMPORTANT |  | 己方 | 可 |
| 增援到达 | `EVA_ReinforcementsHaveArrived` | Reinforcemenets have arrived. | IMPORTANT | 是 | 己方 | 可 |
| 占领科技建筑 | `EVA_TechBuildingCaptured` | Tech building captured. | IMPORTANT | 是 | 己方 | 可 |
| 科技建筑丢失 | `EVA_TechBuildingLost` | Tech building lost. | IMPORTANT | 是 | 己方 | 可 |
| 科技被窃 | `EVA_TechnologyStolen` | Technology stolen. | IMPORTANT | 是 | 己方 | 可 |
| 单位阵亡 | `EVA_UnitLost` | Unit lost. | IMPORTANT |  | 己方 | 可 |
| 占领机场 | `EVA_AirfieldCaptured` | — | NORMAL | 是 | 己方 | 可 |
| 空袭已发起 | `EVA_AirstrikeInitiated` | — | NORMAL | 是 | 己方 | 可 |
| 收到结盟请求 | `EVA_AllianceRequested` | Alliance requested. | NORMAL | 是 | 己方 | 可 |
| 战斗控制上线 | `EVA_BattleControlOnline` | — | NORMAL | 是 | 己方 | 可 |
| 侦测到信标 | `EVA_BeaconDetected` | Beacon detected. | NORMAL | 是 | 全图 | 不可 |
| 占领建筑 | `EVA_BuildingCaptured` | Building Captured. | NORMAL | 是 | 己方 | 可 |
| 建筑被渗透 | `EVA_BuildingInfiltrated` | Building infiltrated. | NORMAL | 是 | 己方 | 可 |
| 超时空传送仪就绪 | `EVA_ChronosphereReady` | Chronosphere ready. | NORMAL | 是 | 己方 | 可 |
| 力场护盾已激活 | `EVA_ForceShieldActivated` | — | NORMAL | 是 | 全图 | 不可 |
| 力场护盾就绪 | `EVA_ForceShieldReady` | — | NORMAL | 是 | 己方 | 可 |
| 基因突变器已激活 | `EVA_GeneticMutatorActivated` | — | NORMAL | 是 | 全图 | 不可 |
| 侦测到基因突变器 | `EVA_GeneticMutatorDetected` | — | NORMAL | 是 | 全图 | 不可 |
| 基因突变器就绪 | `EVA_GeneticMutatorReady` | — | NORMAL | 是 | 己方 | 可 |
| 占领医院 | `EVA_HospitalCaptured` | — | NORMAL | 是 | 己方 | 可 |
| 资金不足 | `EVA_InsufficientFunds` | Insufficient funds. | NORMAL |  | 己方 | 可 |
| 铁幕就绪 | `EVA_IronCurtainReady` | Iron Curtain ready. | NORMAL | 是 | 己方 | 可 |
| 闪电风暴就绪 | `EVA_LightningStormReady` | Lightning Storm ready. | NORMAL | 是 | 己方 | 可 |
| 占领机器商店 | `EVA_MachineShopCaptured` | — | NORMAL | 是 | 己方 | 可 |
| 核弹就绪 | `EVA_NuclearMissileReady` | Nuclear Missile Ready. | NORMAL | 是 | 己方 | 可 |
| 目标完成 | `EVA_ObjectiveComplete` | — | NORMAL | 是 | 己方 | 可 |
| 占领油井 | `EVA_OilRefineryCaptured` | — | NORMAL | 是 | 己方 | 可 |
| 伞兵就绪 | `EVA_ParatroopersReady` | — | NORMAL | 是 | 己方 | 可 |
| 心灵控制器已激活 | `EVA_PsychicDominatorActivated` | — | NORMAL | 是 | 全图 | 不可 |
| 侦测到心灵控制器 | `EVA_PsychicDominatorDetected` | — | NORMAL | 是 | 全图 | 不可 |
| 心灵控制器就绪 | `EVA_PsychicDominatorReady` | — | NORMAL | 是 | 己方 | 可 |
| 增援就绪 | `EVA_ReinforcementsReady` | ReinforcementsReady | NORMAL | 是 | 己方 | 可 |
| 占领维修厂 | `EVA_RepairFacilityCaptured` | — | NORMAL | 是 | 己方 | 可 |
| 遥控坦克恢复 | `EVA_RobotTanksBackOnline` | — | NORMAL | 是 | 己方 | 可 |
| 遥控坦克离线 | `EVA_RobotTanksOffline` | — | NORMAL | 是 | 己方 | 可 |
| 占领秘密实验室 | `EVA_SecretLabCaptured` | — | NORMAL | 是 | 己方 | 可 |
| 间谍机在途 | `EVA_SpyPlaneEnRoute` | — | NORMAL | 是 | 己方 | 可 |
| 间谍机就绪 | `EVA_SpyPlaneReady` | — | NORMAL | 是 | 己方 | 可 |
| 建筑被放弃 | `EVA_StructureAbandoned` | Structure abandoned. | NORMAL | 是 | 己方 | 可 |
| 建筑被进驻 | `EVA_StructureGarrisoned` | Structure garrisoned. | NORMAL | 是 | 己方 | 可 |
| 建筑被修复 | `EVA_StructureRepaired` | — | NORMAL | 是 | 己方 | 可 |
| 天气控制器离线 | `EVA_WeatherControlOffline` | WeatherControlDeviceOffline | NORMAL | 是 | 己方 | 可 |
| 天气控制器不可用 | `EVA_WeatherControlUnavailable` | — | NORMAL | 是 | 己方 | 可 |
| 侦测到天气控制器 | `EVA_WeatherDeviceReady` | Warning:  Weather Control Device detected. | NORMAL | 是 | 己方 | 可 |
| 全军装甲升级 | `EVA_ArmorUpgraded` | Armor upgraded. | LOW |  | 己方 | 可 |
| 防御设施离线 | `EVA_BaseDefensesOffLine` | Base defenses off-line. | LOW |  | 己方 | 可 |
| 已放置信标 | `EVA_BeaconPlaced` | Beacon placed. | LOW |  | 己方 | 可 |
| 桥梁修复 | `EVA_BridgeRepaired` | Bridge repaired. | LOW |  | 己方 | 可 |
| 开始建造 | `EVA_Building` | Building. | LOW |  | 己方 | 可 |
| 被渗透：资金被窃 | `EVA_BuildingInfCashStolen` | Building infiltrated:  Cash stolen. | LOW | 是 | 己方 | 可 |
| 被渗透：雷达被破坏 | `EVA_BuildingInfRadarSabotaged` | Building infiltrated:  Radar sabotaged. | LOW | 是 | 己方 | 可 |
| 被渗透：科技被窃 | `EVA_BuildingInfTechStolen` | Building infiltrated:  Technology stolen. | LOW | 是 | 己方 | 可 |
| 被渗透：电力被破坏 | `EVA_BuildingInfiltratedPowerSabotaged` | Building infiltrated:  Power sabotaged. | LOW | 是 | 己方 | 可 |
| 建筑离线 | `EVA_BuildingOffLine` | Building off-line. | LOW |  | 己方 | 可 |
| 建筑上线 | `EVA_BuildingOnLine` | Building on-line. | LOW |  | 己方 | 可 |
| 已取消 | `EVA_Canceled` | Canceled. | LOW |  | 己方 | 可 |
| 此处无法展开 | `EVA_CannotDeployHere` | Cannot deploy here. | LOW |  | 己方 | 可 |
| 建造完成 | `EVA_ConstructionComplete` | Construction Complete. | LOW |  | 己方 | 可 |
| 全军火力升级 | `EVA_FirepowerUpgraded` | Firepower upgraded. | LOW |  | 己方 | 可 |
| 有新建筑可造 | `EVA_NewConstructionOptions` | New construction options. | LOW | 是 | 己方 | 可 |
| 新集结点已设 | `EVA_NewRallyPointEstablished` | New rally point established. | LOW |  | 己方 | 可 |
| 已暂停 | `EVA_OnHold` | On hold. | LOW |  | 己方 | 可 |
| 盟友被攻击 | `EVA_OurAllyIsUnderAttack` | Our ally is under attack. | LOW | 是 | 己方 | 可 |
| 已设为主建筑 | `EVA_PrimaryBuildingSelected` | Primary building selected. | LOW |  | 己方 | 可 |
| 修复中 | `EVA_Repairing` | Repairing. | LOW |  | 己方 | 可 |
| 正在请求结盟 | `EVA_RequestingAlliance` | Requesting alliance. | LOW |  | 己方 | 可 |
| 请选择目标 | `EVA_SelectTarget` | Select target. | LOW |  | 己方 | 可 |
| 全军速度升级 | `EVA_SpeedUpgraded` | Speed upgraded. | LOW |  | 己方 | 可 |
| 建筑被变卖 | `EVA_StructureSold` | Structure sold. | LOW |  | 己方 | 可 |
| 训练中 | `EVA_Training` | Training. | LOW |  | 己方 | 可 |
| 无法执行 | `EVA_UnableToComply` | Unable to comply, building in progress. | LOW |  | 己方 | 可 |
| 单位装甲升级 | `EVA_UnitArmorUpgraded` | Unit Armor Upgraded | LOW |  | 己方 | 可 |
| 单位火力升级 | `EVA_UnitFirePowerUpgraded` | Unit Fire-Power Upgraded | LOW |  | 己方 | 可 |
| 单位晋升 | `EVA_UnitPromoted` | Unit promoted | LOW |  | 己方 | 可 |
| 单位就绪 | `EVA_UnitReady` | Unit Ready. | LOW |  | 己方 | 可 |
| 单位被修复 | `EVA_UnitRepaired` | Unit repaired. | LOW |  | 己方 | 可 |
| 单位被变卖 | `EVA_UnitSold` | Unit sold | LOW |  | 己方 | 可 |
| 单位速度升级 | `EVA_UnitSpeedUpgraded` | Unit Speed Upgraded | LOW |  | 己方 | 可 |
| 单位升级 | `EVA_UnitUpgraded` | Unit upgraded | LOW |  | 己方 | 可 |
| 剩余 10 分钟 | `EVA_10MinutesRemaining` | 10 minutes remaining. | — |  | 己方 | 可 |
| 剩余 1 分钟 | `EVA_1MinuteRemaining` | 1 minute remaining. | — |  | 己方 | 可 |
| 剩余 20 分钟 | `EVA_20MinutesRemaining` | 20 minutes remaining. | — |  | 己方 | 可 |
| 剩余 2 分钟 | `EVA_2MinutesRemaining` | 2 minutes remaining. | — |  | 己方 | 可 |
| 剩余 3 分钟 | `EVA_3MinutesRemaining` | 3 minutes remaining. | — |  | 己方 | 可 |
| 剩余 4 分钟 | `EVA_4MinutesRemaining` | 4 minutes remaining. | — |  | 己方 | 可 |
| 剩余 5 分钟 | `EVA_5MinutesRemaining` | 5 minutes remaining. | — |  | 己方 | 可 |
| 侦测到敌方装甲营 | `EVA_ArmorBattallianDetected` | Warning:  Enemy Armor Battalion detected. | — |  | 全图 | 不可 |
| 装甲科技被窃（我方升级） | `EVA_ArmorTechStolen` | Armor Technology Stolen:  All units gain armor upgrade. | — |  | 己方 | 可 |
| 超时空矿车离线 | `EVA_ChronoMinerOffline` | Chrono Miner offline. | — |  | 己方 | 可 |
| 关键建筑被毁 | `EVA_CriticalStrucureLost` | Critical structure lost. | — |  | 己方 | 可 |
| 关键单位阵亡 | `EVA_CriticalUnitLost` | Critical unit lost. | — |  | 己方 | 可 |
| 侦测到敌方空军编队 | `EVA_EnemyAirArmadaDetected` | Warning:  Enemy Air Armada detected. | — |  | 全图 | 不可 |
| 敌方基地断电 | `EVA_EnemyBasePoweredDown` | Enemy Base Powered down. | — | 是 | 需渗透 | 推断 |
| 侦测到敌方舰队 | `EVA_EnemyFleetDetected` | Warning:  Enemy Fleet detected. | — |  | 全图 | 不可 |
| 侦测到敌方步兵营 | `EVA_EnemyInfantryBattalionDetected` | Warning:  Enemy Infantry Battalion detected. | — |  | 全图 | 不可 |
| 敌方电力恢复 | `EVA_EnemyPowerRestored` | Enemy Power Restored | — |  | 需渗透 | 推断 |
| 火力科技被窃（我方升级） | `EVA_FirePowerTechStolen` | Fire Power Technology Stolen:  All units gain firepower upgrade. | — |  | 己方 | 可 |
| 收到通讯 | `EVA_IncomingTransmission` | Incoming transmission. | — |  | 己方 | 可 |
| 任务完成 | `EVA_MissionAccomplished` | Mission Accomplished | — |  | 己方 | 可 |
| 任务失败 | `EVA_MissionFailed` | Mission failed. | — |  | 己方 | 可 |
| 新任务目标 | `EVA_NewMissionObjective` | New mission objective received. | — |  | 己方 | 可 |
| 收到新目标 | `EVA_NewObjectiveReceived` | New objective received. | — |  | 己方 | 可 |
| 获得新科技 | `EVA_NewTechnologyAcquired` | New technology acquired. | — | 是 | 己方 | 可 |
| 矿车离线 | `EVA_OreMinerOffLine` | Ore Miner off-line. | — |  | 己方 | 可 |
| 矿车被攻击 | `EVA_OreMinerUnderAttack` | Ore Miner under attack | — |  | 己方 | 可 |
| 基地被攻击 | `EVA_OurBaseIsUnderAttack` | Our base is under attack. | — |  | 己方 | 可 |
| 主目标达成 | `EVA_PrimaryObjectiveAchieved` | Primary objective achieved. | — |  | 己方 | 可 |
| 心灵震荡就绪 | `EVA_PsychicRevealReady` | — | — |  | 己方 | 可 |
| 次目标达成 | `EVA_SecondaryObjectiveAchieved` | Secondary objective achieved. | — |  | 己方 | 可 |
| 第三目标达成 | `EVA_TertiaryObjectiveAchieved` | Tertiary objective achieved. | — |  | 己方 | 可 |
| 计时开始 | `EVA_TimerStarted` | Timer started. | — |  | 己方 | 可 |
| 计时停止 | `EVA_TimerStopped` | Timer stopped. | — |  | 己方 | 可 |
| 升级完成 | `EVA_UpgradeComplete` | Upgrade complete. | — |  | 己方 | 可 |
| 升级进行中 | `EVA_UpgradeInProgress` | Upgrade in progress. | — |  | 己方 | 可 |
| 你胜利了 | `EVA_YouAreVictorious` | You are victorious. | — |  | 己方 | 可 |
| 你失败了 | `EVA_YouHaveLost` | You have lost. | — |  | 己方 | 可 |
| 你已投降 | `EVA_YouHaveResigned` | You have resigned. | — |  | 己方 | 可 |

## 单位出厂报告（87）

含建筑。名字里的 `<Type>` 与 `rulesmd.ini` 的类型节对应，但拼写有出入（`YuriEng`、`BatLabYuri`），需要时对照 `codex/units.md`。

| 单位 | 出现过的名字 | 名称 | 引擎原文 | 优先级 | 可见性 | 可合成 |
|---|---|---|---|---|---|---|
| Aegis | Eva | `Unit_Eva_Aegis` | — | — | 全图 | 不可 |
| AircraftCarrier | Eva | `Unit_Eva_AircraftCarrier` | — | — | 全图 | 不可 |
| Apocalypse | Eva/Sofia | `Unit_Eva_Apocalypse` | — | — | 全图 | 不可 |
| BarracksYuri | Eva/Sofia | `Unit_Eva_BarracksYuri` | — | — | 全图 | 不可 |
| BatLabYuri | Eva/Sofia | `Unit_Eva_BatLabYuri` | — | — | 全图 | 不可 |
| BattleBunker | Eva/Sofia | `Unit_Eva_BattleBunker` | — | — | 全图 | 不可 |
| BattleFortress | Eva/Sofia | `Unit_Eva_BattleFortress` | — | — | 全图 | 不可 |
| BioReactor | Sofia | `Unit_Sofia_BioReactor` | — | — | 全图 | 不可 |
| BioRiactor | Eva | `Unit_Eva_BioRiactor` | — | — | 全图 | 不可 |
| BlackEagle | Eva/Sofia | `Unit_Eva_BlackEagle` | — | — | 全图 | 不可 |
| Boomer | Eva/Sofia | `Unit_Eva_Boomer` | — | — | 全图 | 不可 |
| Boris | Eva/Sofia | `Unit_Eva_Boris` | — | — | 全图 | 不可 |
| Brute | Eva/Sofia | `Unit_Eva_Brute` | — | — | 全图 | 不可 |
| Chaos | Eva | `Unit_Eva_Chaos` | — | — | 全图 | 不可 |
| ChaosDrone | Sofia | `Unit_Sofia_ChaosDrone` | — | — | 全图 | 不可 |
| ChronoLegion | Eva/Sofia | `Unit_Eva_ChronoLegion` | — | — | 全图 | 不可 |
| CloneVat | Sofia | `Unit_Sofia_CloneVat` | — | — | 全图 | 不可 |
| CloningVat | Eva | `Unit_Eva_CloningVat` | — | — | 全图 | 不可 |
| CrazyIvan | Sofia | `Unit_Sofia_CrazyIvan` | — | — | 全图 | 不可 |
| DemoTruck | Eva/Sofia | `Unit_Eva_DemoTruck` | — | — | 全图 | 不可 |
| Desolator | Eva/Sofia | `Unit_Eva_Desolator` | — | — | 全图 | 不可 |
| Destroyer | Eva | `Unit_Eva_Destroyer` | — | — | 全图 | 不可 |
| Dreadnought | Sofia | `Unit_Sofia_Dreadnought` | — | — | 全图 | 不可 |
| Engineer | Eva/Sofia | `Unit_Eva_Engineer` | Sir, this is an engineer.  He can repair any Allied building and once inside an enemy building turn it to our side.  He is much smarter than his Soviet counterpart. | — | 全图 | 不可 |
| FloatDisc | Eva/Sofia | `Unit_Eva_FloatDisc` | — | — | 全图 | 不可 |
| ForceShieldAll | Eva/Sofia | `Unit_Eva_ForceShieldAll` | — | — | 全图 | 不可 |
| ForceShieldSov | Eva/Sofia | `Unit_Eva_ForceShieldSov` | — | — | 全图 | 不可 |
| ForceShieldYur | Eva | `Unit_Eva_ForceShieldYur` | — | — | 全图 | 不可 |
| ForceShieldYuri | Sofia | `Unit_Sofia_ForceShieldYuri` | — | — | 全图 | 不可 |
| GI | Sofia | `Unit_Sofia_GI` | Commander, this Allied GI is a well trained soldier capable of quickly deploying a heavy machine gun when stationed within buildings or deployed with his sandbag nest. | — | 全图 | 不可 |
| GatCannon | Eva/Sofia | `Unit_Eva_GatCannon` | — | — | 全图 | 不可 |
| GatTank | Eva/Sofia | `Unit_Eva_GatTank` | — | — | 全图 | 不可 |
| GeneticMut | Eva/Sofia | `Unit_Eva_GeneticMut` | — | — | 全图 | 不可 |
| GrandCannon | Eva/Sofia | `Unit_Eva_GrandCannon` | — | — | 全图 | 不可 |
| Grinder | Eva/Sofia | `Unit_Eva_Grinder` | — | — | 全图 | 不可 |
| GuardianGI | Eva | `Unit_Eva_GuardianGI` | — | — | 全图 | 不可 |
| GuardianGi | Sofia | `Unit_Sofia_GuardianGi` | — | — | 全图 | 不可 |
| HoverYuri | Eva/Sofia | `Unit_Eva_HoverYuri` | — | — | 全图 | 不可 |
| IFV | Eva | `Unit_Eva_IFV` | — | — | 全图 | 不可 |
| IndustrialPlant | Eva/Sofia | `Unit_Eva_IndustrialPlant` | — | — | 全图 | 不可 |
| Initiate | Eva/Sofia | `Unit_Eva_Initiate` | — | — | 全图 | 不可 |
| Intruder | Sofia | `Unit_Sofia_Intruder` | — | — | 全图 | 不可 |
| Kirov | Eva/Sofia | `Unit_Eva_Kirov` | — | — | 全图 | 不可 |
| LaserCosmo | Eva/Sofia | `Unit_Eva_LaserCosmo` | — | — | 全图 | 不可 |
| Lasher | Eva/Sofia | `Unit_Eva_Lasher` | — | — | 全图 | 不可 |
| MCVYuri | Eva/Sofia | `Unit_Eva_MCVYuri` | — | — | 全图 | 不可 |
| Magnetron | Eva/Sofia | `Unit_Eva_Magnetron` | — | — | 全图 | 不可 |
| MasterMind | Eva/Sofia | `Unit_Eva_MasterMind` | — | — | 全图 | 不可 |
| MirageTank | Eva/Sofia | `Unit_Eva_MirageTank` | — | — | 全图 | 不可 |
| Paratrooper | Eva/Sofia | `Unit_Eva_Paratrooper` | — | — | 全图 | 不可 |
| PrismTank | Sofia | `Unit_Sofia_PrismTank` | — | — | 全图 | 不可 |
| PsiCorpse | Eva/Sofia | `Unit_Eva_PsiCorpse` | — | — | 全图 | 不可 |
| PsychSensor | Sofia | `Unit_Sofia_PsychSensor` | — | — | 全图 | 不可 |
| PsychTower | Sofia | `Unit_Sofia_PsychTower` | — | — | 全图 | 不可 |
| PsychicDomin | Eva/Sofia | `Unit_Eva_PsychicDomin` | — | — | 全图 | 不可 |
| PsychicSensor | Eva | `Unit_Eva_PsychicSensor` | — | — | 全图 | 不可 |
| PsychicTower | Eva | `Unit_Eva_PsychicTower` | — | — | 全图 | 不可 |
| RobotControl | Eva/Sofia | `Unit_Eva_RobotControl` | — | — | 全图 | 不可 |
| RobotTank | Eva/Sofia | `Unit_Eva_RobotTank` | — | — | 全图 | 不可 |
| Rocketeer | Eva/Sofia | `Unit_Eva_Rocketeer` | — | — | 全图 | 不可 |
| SEAL | Eva | `Unit_Eva_SEAL` | — | — | 全图 | 不可 |
| SeaScorpion | Sofia | `Unit_Sofia_SeaScorpion` | — | — | 全图 | 不可 |
| ShockTrooper | Eva/Sofia | `Unit_Eva_ShockTrooper` | — | — | 全图 | 不可 |
| SiegeChopper | Eva/Sofia | `Unit_Eva_SiegeChopper` | — | — | 全图 | 不可 |
| Slave | Eva/Sofia | `Unit_Eva_Slave` | — | — | 全图 | 不可 |
| SlaveMiner | Eva/Sofia | `Unit_Eva_SlaveMiner` | — | — | 全图 | 不可 |
| Sniper | Eva/Sofia | `Unit_Eva_Sniper` | — | — | 全图 | 不可 |
| Spy | Eva/Sofia | `Unit_Eva_Spy` | — | — | 全图 | 不可 |
| SpyPlane | Eva/Sofia | `Unit_Eva_SpyPlane` | — | — | 全图 | 不可 |
| Squid | Sofia | `Unit_Sofia_Squid` | — | — | 全图 | 不可 |
| Sub | Sofia | `Unit_Sofia_Sub` | — | — | 全图 | 不可 |
| SubPen | Eva/Sofia | `Unit_Eva_SubPen` | — | — | 全图 | 不可 |
| TankBunk | Eva/Sofia | `Unit_Eva_TankBunk` | — | — | 全图 | 不可 |
| TankDestroyer | Eva/Sofia | `Unit_Eva_TankDestroyer` | — | — | 全图 | 不可 |
| TechHospital | Eva/Sofia | `Unit_Eva_TechHospital` | — | — | 全图 | 不可 |
| TechMachShop | Eva/Sofia | `Unit_Eva_TechMachShop` | — | — | 全图 | 不可 |
| TechSecretLab | Eva/Sofia | `Unit_Eva_TechSecretLab` | — | — | 全图 | 不可 |
| TerrorDrone | Sofia | `Unit_Sofia_TerrorDrone` | — | — | 全图 | 不可 |
| Terrorist | Eva/Sofia | `Unit_Eva_Terrorist` | — | — | 全图 | 不可 |
| TeslaTank | Eva/Sofia | `Unit_Eva_TeslaTank` | — | — | 全图 | 不可 |
| V3 | Eva/Sofia | `Unit_Eva_V3` | — | — | 全图 | 不可 |
| Virus | Eva/Sofia | `Unit_Eva_Virus` | — | — | 全图 | 不可 |
| WallYuri | Eva/Sofia | `Unit_Eva_WallYuri` | — | — | 全图 | 不可 |
| YuriClone | Eva/Sofia | `Unit_Eva_YuriClone` | — | — | 全图 | 不可 |
| YuriEng | Eva/Sofia | `Unit_Eva_YuriEng` | — | — | 全图 | 不可 |
| YuriPrime | Eva/Sofia | `Unit_Eva_YuriPrime` | — | — | 全图 | 不可 |
| YuriWar | Eva/Sofia | `Unit_Eva_YuriWar` | — | — | 全图 | 不可 |
