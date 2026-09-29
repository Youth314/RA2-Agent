# 副官事件的可见性与可合成性

`codex/eva.md` 的「可见性」与「可合成」两列来自本文件。**一行一条**：

```
事件名 | 可见性 | 可合成 | 依据
```

`可见性`：`己方` / `全图` / `需渗透` / `存疑`。`可合成`：`可` / `推断` / `不可`。

**触发条件不在 `evamd.ini` 里**（那是引擎代码），所以下面这份是人填的初稿，
按名字推断而来，**需要真机核对**。规则文件只告诉我们有哪些事件、引擎自己给的分级与原文。

## 两大类

- **己方事件**：自己的东西永远可见，状态观测就能合成。
- **全图事件**：引擎无条件向所有人播报（超武侦测、危险单位出厂），
  但**我们的观测按迷雾过滤**——所以合成不了，除非引擎把它的播报队列暴露出来。

<!-- 以下按「全图 → 敌方 → 己方」排列，改就是了。-->

EVA_EnemyAirArmadaDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_EnemyFleetDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_EnemyInfantryBattalionDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_ArmorBattallianDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_BeaconDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_ChronosphereActivated | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_ChronosphereDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_ForceShieldActivated | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_GeneticMutatorActivated | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_GeneticMutatorDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_IronCurtainActivated | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_IronCurtainDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_LightningStormCreated | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_NuclearMissileLaunched | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_NuclearSiloDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_PsychicDominatorActivated | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_PsychicDominatorDetected | 全图 | 不可 | 引擎会全图播报，但我们的观测按迷雾过滤，拿不到
EVA_EnemyAllianceFormed | 需渗透 | 推断 | 敌方内部状态；需渗透或盟友视野
EVA_EnemyBasePoweredDown | 需渗透 | 推断 | 敌方内部状态；需渗透或盟友视野
EVA_EnemyPowerRestored | 需渗透 | 推断 | 敌方内部状态；需渗透或盟友视野
EVA_10MinutesRemaining | 己方 | 可 |
EVA_1MinuteRemaining | 己方 | 可 |
EVA_20MinutesRemaining | 己方 | 可 |
EVA_2MinutesRemaining | 己方 | 可 |
EVA_3MinutesRemaining | 己方 | 可 |
EVA_4MinutesRemaining | 己方 | 可 |
EVA_5MinutesRemaining | 己方 | 可 |
EVA_AirfieldCaptured | 己方 | 可 |
EVA_AirstrikeInitiated | 己方 | 可 |
EVA_AllianceBroken | 己方 | 可 |
EVA_AllianceFormed | 己方 | 可 |
EVA_AllianceRequested | 己方 | 可 |
EVA_ArmorTechStolen | 己方 | 可 |
EVA_ArmorUpgraded | 己方 | 可 |
EVA_BaseDefensesOffLine | 己方 | 可 |
EVA_BattleControlOnline | 己方 | 可 |
EVA_BattleControlTerminated | 己方 | 可 |
EVA_BattlefieldControlOnline | 己方 | 可 |
EVA_BeaconPlaced | 己方 | 可 |
EVA_BridgeRepaired | 己方 | 可 |
EVA_Building | 己方 | 可 |
EVA_BuildingCaptured | 己方 | 可 |
EVA_BuildingInfCashStolen | 己方 | 可 |
EVA_BuildingInfRadarSabotaged | 己方 | 可 |
EVA_BuildingInfTechStolen | 己方 | 可 |
EVA_BuildingInfiltrated | 己方 | 可 |
EVA_BuildingInfiltratedPowerSabotaged | 己方 | 可 |
EVA_BuildingOffLine | 己方 | 可 |
EVA_BuildingOnLine | 己方 | 可 |
EVA_Canceled | 己方 | 可 |
EVA_CannotDeployHere | 己方 | 可 |
EVA_CashStolen | 己方 | 可 |
EVA_ChronoMinerOffline | 己方 | 可 |
EVA_ChronosphereReady | 己方 | 可 |
EVA_ConstructionComplete | 己方 | 可 |
EVA_CriticalStrucureLost | 己方 | 可 |
EVA_CriticalUnitLost | 己方 | 可 |
EVA_EstablishBattlefieldControl | 己方 | 可 |
EVA_FirePowerTechStolen | 己方 | 可 |
EVA_FirepowerUpgraded | 己方 | 可 |
EVA_ForceShieldReady | 己方 | 可 |
EVA_GeneticMutatorReady | 己方 | 可 |
EVA_HospitalCaptured | 己方 | 可 |
EVA_IncomingTransmission | 己方 | 可 |
EVA_InsufficientFunds | 己方 | 可 |
EVA_IronCurtainReady | 己方 | 可 |
EVA_LightningStormReady | 己方 | 可 |
EVA_LowPower | 己方 | 可 |
EVA_MachineShopCaptured | 己方 | 可 |
EVA_MissionAccomplished | 己方 | 可 |
EVA_MissionFailed | 己方 | 可 |
EVA_NewConstructionOptions | 己方 | 可 |
EVA_NewMissionObjective | 己方 | 可 |
EVA_NewObjectiveReceived | 己方 | 可 |
EVA_NewRallyPointEstablished | 己方 | 可 |
EVA_NewTechnologyAcquired | 己方 | 可 |
EVA_NewTerrainDiscovered | 己方 | 可 |
EVA_NuclearMissileReady | 己方 | 可 |
EVA_ObjectiveComplete | 己方 | 可 |
EVA_OilRefineryCaptured | 己方 | 可 |
EVA_OnHold | 己方 | 可 |
EVA_OreMinerOffLine | 己方 | 可 |
EVA_OreMinerUnderAttack | 己方 | 可 |
EVA_OurAllyIsUnderAttack | 己方 | 可 |
EVA_OurBaseIsUnderAttack | 己方 | 可 |
EVA_ParatroopersReady | 己方 | 可 |
EVA_PlayerDefeated | 己方 | 可 |
EVA_PlayerResigned | 己方 | 可 |
EVA_PowerSabotaged | 己方 | 可 |
EVA_PrimaryBuildingSelected | 己方 | 可 |
EVA_PrimaryObjectiveAchieved | 己方 | 可 |
EVA_PsychicDominatorReady | 己方 | 可 |
EVA_PsychicRevealReady | 己方 | 可 |
EVA_RadarSabotaged | 己方 | 可 |
EVA_ReinforcementsHaveArrived | 己方 | 可 |
EVA_ReinforcementsReady | 己方 | 可 |
EVA_RepairFacilityCaptured | 己方 | 可 |
EVA_Repairing | 己方 | 可 |
EVA_RequestingAlliance | 己方 | 可 |
EVA_RobotTanksBackOnline | 己方 | 可 |
EVA_RobotTanksOffline | 己方 | 可 |
EVA_SecondaryObjectiveAchieved | 己方 | 可 |
EVA_SecretLabCaptured | 己方 | 可 |
EVA_SelectTarget | 己方 | 可 |
EVA_SpeedUpgraded | 己方 | 可 |
EVA_SpyPlaneEnRoute | 己方 | 可 |
EVA_SpyPlaneReady | 己方 | 可 |
EVA_StructureAbandoned | 己方 | 可 |
EVA_StructureGarrisoned | 己方 | 可 |
EVA_StructureRepaired | 己方 | 可 |
EVA_StructureSold | 己方 | 可 |
EVA_TechBuildingCaptured | 己方 | 可 |
EVA_TechBuildingLost | 己方 | 可 |
EVA_TechnologyStolen | 己方 | 可 |
EVA_TertiaryObjectiveAchieved | 己方 | 可 |
EVA_TimerStarted | 己方 | 可 |
EVA_TimerStopped | 己方 | 可 |
EVA_Training | 己方 | 可 |
EVA_UnableToComply | 己方 | 可 |
EVA_UnitArmorUpgraded | 己方 | 可 |
EVA_UnitFirePowerUpgraded | 己方 | 可 |
EVA_UnitLost | 己方 | 可 |
EVA_UnitPromoted | 己方 | 可 |
EVA_UnitReady | 己方 | 可 |
EVA_UnitRepaired | 己方 | 可 |
EVA_UnitSold | 己方 | 可 |
EVA_UnitSpeedUpgraded | 己方 | 可 |
EVA_UnitUpgraded | 己方 | 可 |
EVA_UpgradeComplete | 己方 | 可 |
EVA_UpgradeInProgress | 己方 | 可 |
EVA_WeatherControlOffline | 己方 | 可 |
EVA_WeatherControlUnavailable | 己方 | 可 |
EVA_WeatherDeviceReady | 己方 | 可 |
EVA_YouAreVictorious | 己方 | 可 |
EVA_YouHaveLost | 己方 | 可 |
EVA_YouHaveResigned | 己方 | 可 |
