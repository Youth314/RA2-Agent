# FocusFire 组合结算验证

日期：2026-10-03。状态：focus_fire v2 离线修复及 11 项相关检查通过；未启动游戏、修改 DLL / 配置、部署或重启 MCP / DSH。本次修改 L1 意图选择与生命周期声明，未改变 Executor、Validator、MicroLayer 或原生协议。旧 Attack 与受控 AttackTarget 的证据边界继续分开，见[Attack 验证](Attack玩家接口验证.md)。

## 问题与当前契约

原 focus_fire 对远于 radius 且 chase=true 的单位发 MoveTo(aggressive)。MicroLayer 将移动到位记为 ARRIVED / goal_satisfied，随后该单位不再参与技法求值；全队移动到位时整个任务 satisfied，却没有提交指定目标 Attack。这是组合任务提前结算问题，不是 DLL 缺少攻击入口。

v2 对当前可见且 Agent ID 匹配的指定敌方对象，在 chase=true 时为每个可用 actor 直接构造一次旧 Attack，由原生攻击任务处理追近与接战。沿用 MicroLayer 的 ENGAGING：目标仍在合法可见集合时保持任务与租约，不因抵达旧坐标而成功，不逐拍重发，也不由 L1 追踪目标位置重置寻路。此处只修复调度逻辑，不新增原版等价或实际开火声明。

chase=false 时保留首次求值的距离筛选：半径内 Attack，超半径者旧 Hold。radius 只用于该筛选，不是武器射程、原生攻击的持续边界或禁追击保证。Hold 的 operation_observed 仅表示旧兼容操作的观察匹配；全部 actor 因超半径执行 Hold 时可能按现有运行时 satisfied，不表示攻击过目标。卡片明确这些限制，技法 version 由 1 改为 2。

指定目标不再合法可见或从开始就不可见时，技法返回空，idle_ends_task=true 使任务以 idle 交还管理，不追加 Hold / Stop，也不把可见性丢失解释为击毁。即使完整 state 仍有隐藏目标，L1 不以其补齐公开目标。释放租约不撤销已经提交的原生命令；需要实际停止时由用户明确调用正式 Stop，且遵守其单车辆支持范围。

未知攻击继续由现有 pending / UNVERIFIED 门控保留，目标不可见不会绕过该门控补发或追加停止。cancel 与 ttl_frames 结束 Agent 管理、释放租约，不停止原生行为。目标连续可见且无 cancel / TTL 时任务可以一直在管；本切片不增加击毁判据、实际 Target 强确认或跨宿主持久任务。

## 最小相关检查

执行以下离线命令，共 11 项通过；全部使用固定合法观测与 FakeExecutor，不访问游戏 / 网络。卡片与检查明确可见期间在管、对象目标及旧操作证据边界。

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest -v \
  tests.test_command.TestFocusFireLifecycle \
  tests.test_tactic_actions.TestCombat.test_focus_fire_needs_a_target \
  tests.test_tactic_actions.TestCombat.test_focus_fire_attacks_the_named_target \
  tests.test_tactic_actions.TestCombat.test_focus_fire_can_stay_put_instead_of_chasing \
  tests.test_tactic_actions.TestCombat.test_focus_fire_does_not_order_when_target_is_not_visible \
  tests.test_command.TestTactics.test_filters_by_query
```

六项 Commander.call 生命周期检查覆盖远近两单位同目标 / 抵达旧格 / 目标换位不重发且租约保留、公开可见性丢失时 idle / 无停止 / 无击毁声明 / 租约释放、首次目标不可见且完整 state 仍有对象、不追击分支的 Hold 兼容与完成依据、未知攻击不重发 / 不因不可见结束 / cancel 不停止，以及 TTL / cancel 结束管理无额外指令。四项技法检查覆盖缺 target 拒绝、远近同目标、chase=false 与目标不可见；一项回归直接受卡片措辞影响的查询。未重跑未修改的 L0、DLL 构建 / 加载、Stop / Attack 真机、身份、通知或其他组合技法检查。

## 限制与后续

默认分支从远目标 MoveTo 改为直接旧 Attack，真实寻路、远目标接战和新版卡片的 DSH 使用未验。旧 Attack/action=8 的 Mission 匹配不能证明指定实际 Target、新输入、开火或击毁；本修复不获得 AttackTarget v1 的双证据，也不扩展其单车辆范围。真实目标变身、旧 DLL 服务端动态目标复查、多态武器及完整宿主生命周期保留原限制。

后续在固定 revision、相关且另获授权的集中场景顺带核对默认远目标集火；不为本次 L1 逻辑另起专门游戏，已通过的 AttackTarget 正例不重跑。开发转入 A2 对象护送 / 建筑保护的离线契约与适配方案，复用既有 T02 人工证据和 Guard / Target 基础；新增 DLL 接口、构建与部署按具体范围另行说明并确认。A1 的 U02 / 动态 Target 等未验边界保留，不标 A1 全部完成。
