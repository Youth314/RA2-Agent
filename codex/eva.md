# 副官事件

由 `corpus/raw/evamd.ini` 生成，不要手改。**可见性与合成性两列来自人写的 `corpus/notes/eva_annotations.md`**，其余都是引擎原文。

共 136 个 `EVA_*` 事件、146 条 `Unit_*_<Type>` 单位出厂报告。

两套机制：`EVA_*` 是全局警告；`Unit_*_<Type>` 是「某单位出厂了」，单位与建筑都有，Eva 与 Sofia 两套副官各一份。这类报告引擎无条件全图播报，**我们拿不到**——观测按迷雾过滤。

`优先级` 与 `排队` 是引擎自己的取值——拿它决定哪些事件值得叫醒模型，不必另立一套。

## 事件

| 事件 | 引擎原文 | 优先级 | 排队 | 可见性 | 可合成 | 依据 |
|---|---|---|---|---|---|---|
| `EVA_BattleControlTerminated` | Battle control terminated. | CRITICAL |  | 己方 | 可 |  |
| `EVA_BattlefieldControlOnline` | BattlefieldControlOnline | CRITICAL |  | 己方 | 可 |  |
| `EVA_ChronosphereActivated` | Warning:  Chronosphere activated. | CRITICAL |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_ChronosphereDetected` | Warning:  Chronosphere detected. | CRITICAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_EstablishBattlefieldControl` | Establishing battlefield control…standby. | CRITICAL |  | 己方 | 可 |  |
| `EVA_IronCurtainActivated` | Warning:  Iron Curtain activated. | CRITICAL |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_IronCurtainDetected` | Warning:  Iron Curtain detected. | CRITICAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_LightningStormCreated` | Warning:  Lightning Storm created. | CRITICAL |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_NuclearMissileLaunched` | Warning:  Nuclear Missile Launched. | CRITICAL |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_AllianceBroken` | Alliance broken. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_AllianceFormed` | Alliance formed. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_CashStolen` | Cash stolen. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_EnemyAllianceFormed` | Enemy alliance formed. | IMPORTANT | 是 | 需渗透 | 推断 | 敌方内部状态；需渗透或盟友视野 |
| `EVA_LowPower` | Low power. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_NewTerrainDiscovered` | New terrain discovered. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_NuclearSiloDetected` | Warning:  Nuclear Silo detected. | IMPORTANT | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_PlayerDefeated` | Player defeated. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_PlayerResigned` | Player resigned. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_PowerSabotaged` | Power sabotaged. | IMPORTANT |  | 己方 | 可 |  |
| `EVA_RadarSabotaged` | Radar sabotaged. | IMPORTANT |  | 己方 | 可 |  |
| `EVA_ReinforcementsHaveArrived` | Reinforcemenets have arrived. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_TechBuildingCaptured` | Tech building captured. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_TechBuildingLost` | Tech building lost. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_TechnologyStolen` | Technology stolen. | IMPORTANT | 是 | 己方 | 可 |  |
| `EVA_UnitLost` | Unit lost. | IMPORTANT |  | 己方 | 可 |  |
| `EVA_AirfieldCaptured` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_AirstrikeInitiated` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_AllianceRequested` | Alliance requested. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_BattleControlOnline` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_BeaconDetected` | Beacon detected. | NORMAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_BuildingCaptured` | Building Captured. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_BuildingInfiltrated` | Building infiltrated. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_ChronosphereReady` | Chronosphere ready. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_ForceShieldActivated` | — | NORMAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_ForceShieldReady` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_GeneticMutatorActivated` | — | NORMAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_GeneticMutatorDetected` | — | NORMAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_GeneticMutatorReady` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_HospitalCaptured` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_InsufficientFunds` | Insufficient funds. | NORMAL |  | 己方 | 可 |  |
| `EVA_IronCurtainReady` | Iron Curtain ready. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_LightningStormReady` | Lightning Storm ready. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_MachineShopCaptured` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_NuclearMissileReady` | Nuclear Missile Ready. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_ObjectiveComplete` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_OilRefineryCaptured` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_ParatroopersReady` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_PsychicDominatorActivated` | — | NORMAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_PsychicDominatorDetected` | — | NORMAL | 是 | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_PsychicDominatorReady` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_ReinforcementsReady` | ReinforcementsReady | NORMAL | 是 | 己方 | 可 |  |
| `EVA_RepairFacilityCaptured` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_RobotTanksBackOnline` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_RobotTanksOffline` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_SecretLabCaptured` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_SpyPlaneEnRoute` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_SpyPlaneReady` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_StructureAbandoned` | Structure abandoned. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_StructureGarrisoned` | Structure garrisoned. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_StructureRepaired` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_WeatherControlOffline` | WeatherControlDeviceOffline | NORMAL | 是 | 己方 | 可 |  |
| `EVA_WeatherControlUnavailable` | — | NORMAL | 是 | 己方 | 可 |  |
| `EVA_WeatherDeviceReady` | Warning:  Weather Control Device detected. | NORMAL | 是 | 己方 | 可 |  |
| `EVA_ArmorUpgraded` | Armor upgraded. | LOW |  | 己方 | 可 |  |
| `EVA_BaseDefensesOffLine` | Base defenses off-line. | LOW |  | 己方 | 可 |  |
| `EVA_BeaconPlaced` | Beacon placed. | LOW |  | 己方 | 可 |  |
| `EVA_BridgeRepaired` | Bridge repaired. | LOW |  | 己方 | 可 |  |
| `EVA_Building` | Building. | LOW |  | 己方 | 可 |  |
| `EVA_BuildingInfCashStolen` | Building infiltrated:  Cash stolen. | LOW | 是 | 己方 | 可 |  |
| `EVA_BuildingInfRadarSabotaged` | Building infiltrated:  Radar sabotaged. | LOW | 是 | 己方 | 可 |  |
| `EVA_BuildingInfTechStolen` | Building infiltrated:  Technology stolen. | LOW | 是 | 己方 | 可 |  |
| `EVA_BuildingInfiltratedPowerSabotaged` | Building infiltrated:  Power sabotaged. | LOW | 是 | 己方 | 可 |  |
| `EVA_BuildingOffLine` | Building off-line. | LOW |  | 己方 | 可 |  |
| `EVA_BuildingOnLine` | Building on-line. | LOW |  | 己方 | 可 |  |
| `EVA_Canceled` | Canceled. | LOW |  | 己方 | 可 |  |
| `EVA_CannotDeployHere` | Cannot deploy here. | LOW |  | 己方 | 可 |  |
| `EVA_ConstructionComplete` | Construction Complete. | LOW |  | 己方 | 可 |  |
| `EVA_FirepowerUpgraded` | Firepower upgraded. | LOW |  | 己方 | 可 |  |
| `EVA_NewConstructionOptions` | New construction options. | LOW | 是 | 己方 | 可 |  |
| `EVA_NewRallyPointEstablished` | New rally point established. | LOW |  | 己方 | 可 |  |
| `EVA_OnHold` | On hold. | LOW |  | 己方 | 可 |  |
| `EVA_OurAllyIsUnderAttack` | Our ally is under attack. | LOW | 是 | 己方 | 可 |  |
| `EVA_PrimaryBuildingSelected` | Primary building selected. | LOW |  | 己方 | 可 |  |
| `EVA_Repairing` | Repairing. | LOW |  | 己方 | 可 |  |
| `EVA_RequestingAlliance` | Requesting alliance. | LOW |  | 己方 | 可 |  |
| `EVA_SelectTarget` | Select target. | LOW |  | 己方 | 可 |  |
| `EVA_SpeedUpgraded` | Speed upgraded. | LOW |  | 己方 | 可 |  |
| `EVA_StructureSold` | Structure sold. | LOW |  | 己方 | 可 |  |
| `EVA_Training` | Training. | LOW |  | 己方 | 可 |  |
| `EVA_UnableToComply` | Unable to comply, building in progress. | LOW |  | 己方 | 可 |  |
| `EVA_UnitArmorUpgraded` | Unit Armor Upgraded | LOW |  | 己方 | 可 |  |
| `EVA_UnitFirePowerUpgraded` | Unit Fire-Power Upgraded | LOW |  | 己方 | 可 |  |
| `EVA_UnitPromoted` | Unit promoted | LOW |  | 己方 | 可 |  |
| `EVA_UnitReady` | Unit Ready. | LOW |  | 己方 | 可 |  |
| `EVA_UnitRepaired` | Unit repaired. | LOW |  | 己方 | 可 |  |
| `EVA_UnitSold` | Unit sold | LOW |  | 己方 | 可 |  |
| `EVA_UnitSpeedUpgraded` | Unit Speed Upgraded | LOW |  | 己方 | 可 |  |
| `EVA_UnitUpgraded` | Unit upgraded | LOW |  | 己方 | 可 |  |
| `EVA_10MinutesRemaining` | 10 minutes remaining. | — |  | 己方 | 可 |  |
| `EVA_1MinuteRemaining` | 1 minute remaining. | — |  | 己方 | 可 |  |
| `EVA_20MinutesRemaining` | 20 minutes remaining. | — |  | 己方 | 可 |  |
| `EVA_2MinutesRemaining` | 2 minutes remaining. | — |  | 己方 | 可 |  |
| `EVA_3MinutesRemaining` | 3 minutes remaining. | — |  | 己方 | 可 |  |
| `EVA_4MinutesRemaining` | 4 minutes remaining. | — |  | 己方 | 可 |  |
| `EVA_5MinutesRemaining` | 5 minutes remaining. | — |  | 己方 | 可 |  |
| `EVA_ArmorBattallianDetected` | Warning:  Enemy Armor Battalion detected. | — |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_ArmorTechStolen` | Armor Technology Stolen:  All units gain armor upgrade. | — |  | 己方 | 可 |  |
| `EVA_ChronoMinerOffline` | Chrono Miner offline. | — |  | 己方 | 可 |  |
| `EVA_CriticalStrucureLost` | Critical structure lost. | — |  | 己方 | 可 |  |
| `EVA_CriticalUnitLost` | Critical unit lost. | — |  | 己方 | 可 |  |
| `EVA_EnemyAirArmadaDetected` | Warning:  Enemy Air Armada detected. | — |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_EnemyBasePoweredDown` | Enemy Base Powered down. | — | 是 | 需渗透 | 推断 | 敌方内部状态；需渗透或盟友视野 |
| `EVA_EnemyFleetDetected` | Warning:  Enemy Fleet detected. | — |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_EnemyInfantryBattalionDetected` | Warning:  Enemy Infantry Battalion detected. | — |  | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到 |
| `EVA_EnemyPowerRestored` | Enemy Power Restored | — |  | 需渗透 | 推断 | 敌方内部状态；需渗透或盟友视野 |
| `EVA_FirePowerTechStolen` | Fire Power Technology Stolen:  All units gain firepower upgrade. | — |  | 己方 | 可 |  |
| `EVA_IncomingTransmission` | Incoming transmission. | — |  | 己方 | 可 |  |
| `EVA_MissionAccomplished` | Mission Accomplished | — |  | 己方 | 可 |  |
| `EVA_MissionFailed` | Mission failed. | — |  | 己方 | 可 |  |
| `EVA_NewMissionObjective` | New mission objective received. | — |  | 己方 | 可 |  |
| `EVA_NewObjectiveReceived` | New objective received. | — |  | 己方 | 可 |  |
| `EVA_NewTechnologyAcquired` | New technology acquired. | — | 是 | 己方 | 可 |  |
| `EVA_OreMinerOffLine` | Ore Miner off-line. | — |  | 己方 | 可 |  |
| `EVA_OreMinerUnderAttack` | Ore Miner under attack | — |  | 己方 | 可 |  |
| `EVA_OurBaseIsUnderAttack` | Our base is under attack. | — |  | 己方 | 可 |  |
| `EVA_PrimaryObjectiveAchieved` | Primary objective achieved. | — |  | 己方 | 可 |  |
| `EVA_PsychicRevealReady` | — | — |  | 己方 | 可 |  |
| `EVA_SecondaryObjectiveAchieved` | Secondary objective achieved. | — |  | 己方 | 可 |  |
| `EVA_TertiaryObjectiveAchieved` | Tertiary objective achieved. | — |  | 己方 | 可 |  |
| `EVA_TimerStarted` | Timer started. | — |  | 己方 | 可 |  |
| `EVA_TimerStopped` | Timer stopped. | — |  | 己方 | 可 |  |
| `EVA_UpgradeComplete` | Upgrade complete. | — |  | 己方 | 可 |  |
| `EVA_UpgradeInProgress` | Upgrade in progress. | — |  | 己方 | 可 |  |
| `EVA_YouAreVictorious` | You are victorious. | — |  | 己方 | 可 |  |
| `EVA_YouHaveLost` | You have lost. | — |  | 己方 | 可 |  |
| `EVA_YouHaveResigned` | You have resigned. | — |  | 己方 | 可 |  |

## 单位出厂报告（146）

含建筑。名字里的 `<Type>` 与 `rulesmd.ini` 的类型节对应，但拼写有出入（`YuriEng`、`BatLabYuri`），需要时对照 `codex/units.md`。

| 名称 | 单位 | 副官 | 引擎原文 | 优先级 | 可见性 | 可合成 |
|---|---|---|---|---|---|---|
| `Unit_Eva_Aegis` | Aegis | Eva | — | — | 全图 | 不可 |
| `Unit_Eva_AircraftCarrier` | AircraftCarrier | Eva | — | — | 全图 | 不可 |
| `Unit_Eva_Apocalypse` | Apocalypse | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Apocalypse` | Apocalypse | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_BarracksYuri` | BarracksYuri | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_BarracksYuri` | BarracksYuri | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_BatLabYuri` | BatLabYuri | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_BatLabYuri` | BatLabYuri | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_BattleBunker` | BattleBunker | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_BattleBunker` | BattleBunker | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_BattleFortress` | BattleFortress | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_BattleFortress` | BattleFortress | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_BioReactor` | BioReactor | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_BioRiactor` | BioRiactor | Eva | — | — | 全图 | 不可 |
| `Unit_Eva_BlackEagle` | BlackEagle | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_BlackEagle` | BlackEagle | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Boomer` | Boomer | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Boomer` | Boomer | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Boris` | Boris | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Boris` | Boris | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Brute` | Brute | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Brute` | Brute | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Chaos` | Chaos | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_ChaosDrone` | ChaosDrone | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_ChronoLegion` | ChronoLegion | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_ChronoLegion` | ChronoLegion | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_CloneVat` | CloneVat | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_CloningVat` | CloningVat | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_CrazyIvan` | CrazyIvan | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_DemoTruck` | DemoTruck | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_DemoTruck` | DemoTruck | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Desolator` | Desolator | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Desolator` | Desolator | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Destroyer` | Destroyer | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Dreadnought` | Dreadnought | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Engineer` | Engineer | Eva | Sir, this is an engineer.  He can repair any Allied building and once inside an enemy building turn it to our side.  He is much smarter than his Soviet counterpart. | — | 全图 | 不可 |
| `Unit_Sofia_Engineer` | Engineer | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_FloatDisc` | FloatDisc | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_FloatDisc` | FloatDisc | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_ForceShieldAll` | ForceShieldAll | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_ForceShieldAll` | ForceShieldAll | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_ForceShieldSov` | ForceShieldSov | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_ForceShieldSov` | ForceShieldSov | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_ForceShieldYur` | ForceShieldYur | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_ForceShieldYuri` | ForceShieldYuri | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_GI` | GI | Zofia | Commander, this Allied GI is a well trained soldier capable of quickly deploying a heavy machine gun when stationed within buildings or deployed with his sandbag nest. | — | 全图 | 不可 |
| `Unit_Eva_GatCannon` | GatCannon | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_GatCannon` | GatCannon | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_GatTank` | GatTank | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_GatTank` | GatTank | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_GeneticMut` | GeneticMut | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_GeneticMut` | GeneticMut | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_GrandCannon` | GrandCannon | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_GrandCannon` | GrandCannon | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Grinder` | Grinder | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Grinder` | Grinder | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_GuardianGI` | GuardianGI | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_GuardianGi` | GuardianGi | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_HoverYuri` | HoverYuri | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_HoverYuri` | HoverYuri | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_IFV` | IFV | Eva | — | — | 全图 | 不可 |
| `Unit_Eva_IndustrialPlant` | IndustrialPlant | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_IndustrialPlant` | IndustrialPlant | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Initiate` | Initiate | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Initiate` | Initiate | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_Intruder` | Intruder | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Kirov` | Kirov | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Kirov` | Kirov | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_LaserCosmo` | LaserCosmo | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_LaserCosmo` | LaserCosmo | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Lasher` | Lasher | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Lasher` | Lasher | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_MCVYuri` | MCVYuri | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_MCVYuri` | MCVYuri | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Magnetron` | Magnetron | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Magnetron` | Magnetron | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_MasterMind` | MasterMind | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_MasterMind` | MasterMind | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_MirageTank` | MirageTank | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_MirageTank` | MirageTank | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Paratrooper` | Paratrooper | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Paratrooper` | Paratrooper | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_PrismTank` | PrismTank | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_PsiCorpse` | PsiCorpse | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_PsiCorpse` | PsiCorpse | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_PsychSensor` | PsychSensor | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_PsychTower` | PsychTower | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_PsychicDomin` | PsychicDomin | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_PsychicDomin` | PsychicDomin | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_PsychicSensor` | PsychicSensor | Eva | — | — | 全图 | 不可 |
| `Unit_Eva_PsychicTower` | PsychicTower | Eva | — | — | 全图 | 不可 |
| `Unit_Eva_RobotControl` | RobotControl | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_RobotControl` | RobotControl | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_RobotTank` | RobotTank | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_RobotTank` | RobotTank | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Rocketeer` | Rocketeer | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Rocketeer` | Rocketeer | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_SEAL` | SEAL | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_SeaScorpion` | SeaScorpion | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_ShockTrooper` | ShockTrooper | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_ShockTrooper` | ShockTrooper | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_SiegeChopper` | SiegeChopper | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_SiegeChopper` | SiegeChopper | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Slave` | Slave | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Slave` | Slave | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_SlaveMiner` | SlaveMiner | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_SlaveMiner` | SlaveMiner | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Sniper` | Sniper | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Sniper` | Sniper | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Spy` | Spy | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Spy` | Spy | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_SpyPlane` | SpyPlane | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_SpyPlane` | SpyPlane | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_Squid` | Squid | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_Sub` | Sub | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_SubPen` | SubPen | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_SubPen` | SubPen | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_TankBunk` | TankBunk | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_TankBunk` | TankBunk | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_TankDestroyer` | TankDestroyer | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_TankDestroyer` | TankDestroyer | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_TechHospital` | TechHospital | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_TechHospital` | TechHospital | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_TechMachShop` | TechMachShop | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_TechMachShop` | TechMachShop | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_TechSecretLab` | TechSecretLab | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_TechSecretLab` | TechSecretLab | Zofia | — | — | 全图 | 不可 |
| `Unit_Sofia_TerrorDrone` | TerrorDrone | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Terrorist` | Terrorist | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Terrorist` | Terrorist | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_TeslaTank` | TeslaTank | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_TeslaTank` | TeslaTank | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_V3` | V3 | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_V3` | V3 | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_Virus` | Virus | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_Virus` | Virus | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_WallYuri` | WallYuri | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_WallYuri` | WallYuri | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_YuriClone` | YuriClone | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_YuriClone` | YuriClone | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_YuriEng` | YuriEng | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_YuriEng` | YuriEng | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_YuriPrime` | YuriPrime | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_YuriPrime` | YuriPrime | Zofia | — | — | 全图 | 不可 |
| `Unit_Eva_YuriWar` | YuriWar | Eva | — | — | 全图 | 不可 |
| `Unit_Sofia_YuriWar` | YuriWar | Zofia | — | — | 全图 | 不可 |
