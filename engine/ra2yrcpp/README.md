# ra2yrcpp 本地扩展

本目录保存可追溯源码补丁，不保存编译 DLL。Guard v1 属于 S3 实验接口；编译与离线测试不能证明原版行为等价，真机验证记录见 [.agents/notes/验证/Guard接口验证.md](../../.agents/notes/验证/Guard接口验证.md)。

| 补丁 | 上游与固定版本 | 应用位置 |
|---|---|---|
| patches/guard-v1-engine.patch | ra2yrcpp ee215f5a01f709c52b1fe4dd333d16cbe5d5f146 | ra2yrcpp 根目录 |
| patches/guard-v1-protocol.patch | ra2yrproto 0ad72455bcdcf5626d0e17c3311ea82556da2ad3 | src/protocol/ra2yrproto 子模块 |

上游及子模块均附 GNU GPL v3 许可证；COPYING 从固定 ra2yrcpp 源码复制。补丁中的上游上下文保留原许可，本地扩展采用同一许可。源码入口和依赖准备见 [DLL 构建准备](../../.agents/notes/环境/DLL构建准备.md)。

先使用 tools/build_engine.sh 准备未修改基线，再运行 `python3 tools/build_guard_engine.py`。脚本复制独立源码目录、应用两份补丁并复用已准备依赖；重复运行要求源码差异与补丁严格一致，不覆盖未识别的修改。构建不联网、不更改系统依赖、不替换游戏 DLL。

协议沿用 UnitOrder，增加 action=13/14 和字段 expected_native_id=5、expected_house=6、basis_frame=7；GameState.guard_interface_version=17 声明 v1，己方 Object.native_id=21 为可选 UniqueID 回读。通过固定 YRpp 布局读取字段，避免跨编译器直接 Fetch_ID 虚调用；合法 Cell 经固定 ClickMission 编码到 Target，Destination 保持空。字段与枚举仅为本地扩展，不代表上游已采用。版本缺失时 L0 拒绝 Guard，不回退任意 MissionClicked。

## Stop v1 切片

`patches/stop-v1-engine.patch` 与 `patches/stop-v1-protocol.patch` 相对上表同一未修改基线生成，包含 Guard v1；不得在 Guard 补丁之上叠加。`ENGINE_FEATURE=stop PYTHONDONTWRITEBYTECODE=1 python3 tools/build_guard_engine.py` 生成独立源码、构建目录和 stop-v1 产物，默认仍构建 Guard。Stop 的 action=15、GameState.stop_interface_version=18 独立于 Guard 版本；Idle 使用既有 Event.Target.whom 字段回读。原 STOP action=10 保留。

当前 Stop v1 已长期启用，编译、相关离线回归、Grizzly 三项限定真机对照及运行加载检查通过；证据与限制见 [Stop 玩家接口验证](../../.agents/notes/验证/Stop玩家接口验证.md)，部署指纹与回滚见 [Stop 部署与对照](../../.agents/notes/环境/Stop部署与对照.md)。

## Target v1 只读切片

`patches/target-v1-engine.patch` 与 `patches/target-v1-protocol.patch` 相对同一未修改固定基线生成，包含 Stop/Guard v1；不与旧补丁叠加。新字段为 `Object.actual_target=22` 和 `GameState.target_observation_version=19`，只读己方 actor 的合法当前对象目标，区分未提供、不可观测、无目标和对象；RTTI=52 的原版引用与具体对象类型分开，L1 经 Observer 投影为稳定 Agent ID。Cell、灰雾/隐形/伪装或无法确认的目标不导出有效引用，不代表受控 Attack 已完成。

`ENGINE_FEATURE=target PYTHONDONTWRITEBYTECODE=1 python3 tools/build_guard_engine.py` 生成独立源码、构建与 target-v1 产物。补丁新增纯策略头文件，构建脚本在复制的源码仓库中用 intent-to-add 纳入 diff 校验，不提交该临时仓库；其他版本构建路径不变。布局 static_assert 使用锁定 YRpp/i686 偏移。相关离线检查、独立构建与限定双侧临时加载/MTNK→AMCV 非空目标回读通过，已恢复 Stop v1；指纹、合法观测及未验边界见 [U08 验证](../../.agents/notes/验证/U08实际目标回读验证.md)。

## Attack v1 功能组

`patches/attack-v1-engine.patch` 与 `patches/attack-v1-protocol.patch` 包含 Target/Stop/Guard，相对同一固定未修改基线生成，不叠加旧补丁。`ENGINE_FEATURE=attack PYTHONDONTWRITEBYTECODE=1 python3 tools/build_guard_engine.py` 创建独立源码、build 和 attack-v1 产物；已配置的同版本失败构建可使用 `ENGINE_RESUME_BUILD=1` 续编，脚本核对 source/version 并继续校验完整源码差异，不重复配置。新纯策略与游戏线程目标门由新头文件提供，House 关系调用使用固定 ABI，布局漂移由断言阻断。

新增 action=16、GameState.attack_interface_version=20、内部 Object.order_target_native_id=23 和 UnitOrder 目标身份字段 8–10。只支持单个己方车辆点名合法可见敌方车辆/建筑；公开 Observation 不携带内部目标身份。新请求复查 live 成员、目标身份、敌对关系、可见性与变身；不使用旧缓存取敌方坐标。相关离线检查与独立构建通过，产物未部署/加载，真机效果未验，完整指纹与范围见[Attack 验证](../../.agents/notes/验证/Attack玩家接口验证.md)。

## 对象警戒 v1 功能组

`patches/object-guard-v1-engine.patch` / `object-guard-v1-protocol.patch` 包含既有 Guard / Stop / Target / Attack，相对同一固定干净基线生成。`ENGINE_FEATURE=object-guard ENGINE_BUILD_JOBS=2 PYTHONDONTWRITEBYTECODE=1 python3 tools/build_guard_engine.py` 使用独立 sources / build / artifacts 目录和缓存依赖，不部署或修改游戏配置。

新增 action=17、GameState.object_guard_interface_version=21，复用 UnitOrder 目标身份字段 8–10 与己方 Object.native_id。护送己方车辆和保护己方建筑共用一个受控对象输入，游戏线程复查成员 / 归属 / 身份 / 类型 / 存活 / 变身 / 地图位置，经固定 ClickMission ABI 提交 Area_Guard，对象 target 与空 destination / follow 分开。回执仅确认新输入，不借实际攻击 Target 宣称护送效果。必要离线检查与独立构建通过，未部署 / 加载，指纹及候选批次见[对象警戒验证](../../.agents/notes/验证/对象警戒接口验证.md)。
