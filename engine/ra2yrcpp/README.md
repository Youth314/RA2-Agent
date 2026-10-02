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

当前仅编译与相关离线回归通过，尚未部署；证据、指纹与限制见 [Stop 玩家接口验证](../../.agents/notes/验证/Stop玩家接口验证.md)，临时环境范围及回滚见 [Stop 部署与对照](../../.agents/notes/环境/Stop部署与对照.md)。
