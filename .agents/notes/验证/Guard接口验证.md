# Guard 接口验证

日期：2026-10-02。范围：S3 GuardCurrent / GuardPosition 首版受控接口、己方原版身份回读与可追溯 DLL 补丁。状态：相关离线回归、编译、单个 Grizzly 的限定双实例真机验证及 CMIN / Engineer-FV 的 GuardCurrent 多态正例通过；空 FV 对照按用户决定跳过，完整车辆多态、所有服务端拒绝边界与完整联机同步未验。本轮临时替换两侧 DLL 并启动测试，已停止本轮进程并恢复原 DLL、启动配置及硬链接关系，未安装新依赖或改变 DSH。基线的限定加载证据见[基线 DLL 加载验证](基线DLL加载验证.md)，不得用于替代新操作验收。

实现提交：d5a145e；基线构建与加载记录提交：a0d8cbf。车辆多态输入样本与回归提交：df5534c。测试样本与源码补丁已入库，临时 DLL 和完整备份日志保留在忽略目录。

## 请求、回读与边界

L1 使用 GuardCurrent(units=(agent_id,)) 或 GuardPosition(units=(agent_id,), cell=(x,y))；复用 Intent 信封、日志、作用域和现有租约链。模型仍只调用技法，当前没有新增公开技法或工具。两类意图只建立一次原版输入，未承诺持续维持、到达指定地点或完成采矿与维修。GuardPosition 不是原版多节点路径或 append 操作。

| 项目 | 首版契约 |
|---|---|
| 能力声明 | GameState.guard_interface_version=1；缺失、0 或未知版本明确 unsupported |
| 适用对象 | 每条请求一个己方存活、在图且非变身中的 UnitClass；不接收 Infantry、Aircraft 或建筑，不保证所有车辆子类型已实测 |
| 身份 | L1 传 Agent ID；L0 新鲜观测解析 pointer 与己方 Object.native_id；DLL 在游戏线程重查对象集合、归属和 UniqueID |
| 协议 | UnitOrder action=13/14；expected_native_id=5、expected_house=6、basis_frame=7；目标对象字段必须为空 |
| GuardCurrent | 无坐标载荷；DLL 使用执行时 actor.Location 选当前格，避免排队期间位置过期 |
| GuardPosition | 整数格坐标由 L0 转格中心；DLL 重查MapCoordBounds 格坐标包围范围、有效 Cell 和坐标范围，不开放任意 Mission |
| 时效 | DLL 拒绝未来 basis_frame 或超过 150 游戏帧的依据；这不是完整局次 nonce |
| 输入路径 | 经受控 UnitOrder 调用固定 Area_Guard 的既有 ClickMission ABI；合法 Cell 放入 packed Target 参数，Destination 为空；检查返回值，不使用通用 MissionClicked 请求 |
| 最少回读 | Object 字段 21 为 optional uint32 native_id，通过固定 YRpp 布局读取 UniqueID，仅回读己方 Techno；缺失与 0 区分；本轮输入 whom ID 已验证对应关系 |

IdentityTable 在相同指针的两个已知 native_id 不同时立即退役旧 Agent ID，避免发送前的新鲜状态把旧意图转给新单位。缺失可选字段不擦除已有原版 ID；旧 DLL 保留原识别方式。跨指针变身仍按既有位置与类型启发式配对，延续 Agent ID 后更新原版 ID；它不是所有变身的确定性关联。显式指针复用不会参加该变身配对，vanished 表示旧身份退役，不证明原单位死亡。

## 回执含义

ExecutionOutcome.receipt 保持 observed_match，新增 evidence=native_input_observed。匹配条件为当前玩家的新 MegaMission 输入、mission=Area_Guard、whom RTTI=52 与本次 native_id 相符、事件帧不早于依据帧、合法地点；GuardPosition 还要求目标格完全相同。回读对象必须仍与原身份和归属匹配。GuardCurrent 接受有效的执行时锚点，不以发送前旧格要求锚点相等。

输入确认不等于对象当前 Mission、实际抵达、采矿往返、维修效果或持续护送。输入事件没有请求 ID，人工同时向相同单位下达相同操作时仍可能无法区分来源；验证期间必须由单一执行者控制该单位，后续如需强请求关联须增加独立回执。事件短暂或丢失可能导致 unverified，不能因为超时自动重发。

发送前已有事件的语义签名被排除，签名包含 house_index/timing/event_type/mega_mission，不含 Frame、列表来源、raw 或 is_executed；实测同一输入从 out 转到 do 时 Frame 可被重新调度，Timing 和载荷保持一致，因此帧号变化的旧输入也被排除。不会用旧 AREA_GUARD、旧 destination 或 is_executed 判定成功。没有持续 Target/Follow、乘员模式、矿量或保护锚点回读。

现有 MicroLayer 将非移动/攻击的一次操作按 operation_observed 结算并可释放任务租约；这里表示输入观测完成，游戏行为可能继续，也可能被后续自动层覆盖。没有新增长期保护任务，也没有改变 cancel 的含义。持久任务和自动经济迁移在 S4 单独处理。

## 离线证据

永久测试为 [test_guard_interface.py](../../../tests/test_guard_interface.py)，28 项测试，包含合成状态、假客户端与真机最小样本；原版输入字节依据见[原版操作测绘](原版操作测绘.md)，新增 [guard_interface_native.json](../../../tests/data/guard_interface_native.json) 保存三次 Grizzly 和两次 CMIN / Engineer-FV 的新接口输入及己方对象回读，含场景和 DLL 指纹；它是输入样本，不是完整回放。

```sh
PYTHONPATH=src python3 -m unittest tests.test_guard_interface tests.test_identity tests.test_intents tests.test_payloads tests.test_wire tests.test_validate tests.test_state tests.test_native_events tests.test_executor tests.test_micro tests.test_autopilot tests.test_command tests.test_mcp tests.test_replay
```

结果：521 项通过，未运行全量测试。覆盖版本与可选字段解析、非法线类型/范围、载荷字段、序列化、客户端路由、单车辆限制、越权不可放宽、对象不可用、地点边界、纯计划无 I/O、新输入与错误事件、旧事件 out/do 转移、未知结果单次发送、发送前指针复用拒绝以及变身身份兼容、同一旧事件重新调度为未来帧、Commander.call → MicroLayer → Executor 完整调用与作用域/租约结算、空单位/无地图/参数错误拒绝、五次真实输入与原版 ID/目标格关联、HARVEST 等多态效果任务不作为输入回执的额外限制。新增真实样本回归初跑沿用了合成坦克的固定指针，已修正测试装配为样本真实 pointer、house_index 与 144×144 地图后重跑通过；未因此修改运行时实现。WebSocket 回环测试在沙箱内因 socket 权限失败，已获执行批准后重跑通过；不存在名为 tests.test_client 的模块，最终命令使用实际 tests.test_wire 与 Guard 客户端路由测试。

## 构建与可追溯产物

永久补丁、许可证与固定版本在 [engine/ra2yrcpp](../../../engine/ra2yrcpp/README.md)；复跑入口为 `python3 tools/build_guard_engine.py`。先准备[未修改基线](../环境/DLL构建准备.md)，脚本复制独立源码、应用两份补丁并复用 protobuf、运行库副本与 GoogleTest 缓存，不联网、安装或部署。已有源码差异必须与补丁一致，拒绝未知修改，不自动 reset。

已完成两次脚本构建，复跑哈希一致；仅证明当前工作区的增量复跑，不声称跨机器可复现哈希。构建检查通过：PE32 i386 DLL、预期四项 Windows 导入、hook section、七项 hook 导出、单一版本资源。当前构建的限定加载及 Guard 正例证据见下节。直接 Fetch_ID 虚调用已移除；对象集合、UniqueID 回读、格坐标校验与固定参数位置已经过本轮单车辆正例，不代表所有类型和服务端拒绝均实测。manifest.game_loaded=False 表示构建脚本不负责加载，实际加载证据由本记录单独维护。

| 产物 | 值或路径 |
|---|---|
| DLL | .agents/tmp/engine-build/artifacts/guard-v1/libra2yrcpp.dll |
| SHA-256 | 862a8c318a7193c5b4a6ec6899af26ecebef47b05b0270ce86debef6ef11010c |
| 大小 | 8246933 bytes，约 7.9 MiB |
| 清单与日志 | 同目录 manifest.json；.agents/tmp/engine-build/logs/guard-* |
| 独立源码 | .agents/tmp/engine-build/sources/ra2yrcpp-guard |

本轮复用已安装工具与依赖；加入独立源码和构建、尚未积累本轮真机备份时 .agents/tmp/engine-build 合计约 765 MiB；逐轮备份另计。研究源码与未修改基线保持独立，游戏仍使用恢复后的原 DLL。

## 限定真机结果与修复经验

用户已确认临时替换和测试。成功记录为 .agents/tmp/engine-build/backups/guard-20261002-164406/validation.json；同目录含原 DLL/配置备份、前后日志、逐次 guard-observations.jsonl、guard-decisions.jsonl 与三份回执状态二进制。Alpha=Alliance、house_index=1；Beta=Americans、house_index=0，均 stage=2、single_step=False、地图 144×144、类型表 3875 项、己方对象 11 个。两侧 capability=1，己方 native_id 均非零，非己方没有该字段。

测试只在独立注册表注册 tests/guard_probe_tactics.py 的两个确定性函数，不加入 builtin/local 正式目录或 DSH。测试注册表允许 Commander.call 进入真实受理路径；依次经过作用域与租约、技法产出意图、L0 新鲜读取和 DLL。未运行模型、自动经济或 Beta 的单位命令。Grizzly 的 native_id=1043819；两侧通过初始 house_index、类型和精确世界坐标唯一配对，再各自使用进程内指针持续观察，未把跨进程指针视为同一地址。

| 操作 | 依据帧 → 输入观测帧 | 原版输入 | 效果证据 |
|---|---|---|---|
| GuardCurrent 初始位置 | 123 → 127 | MegaMission/Area_Guard；Target=(30,80)，Destination=null；out frame=124 | 输入匹配，此时单位仍为 GUARD，不能当成已执行任务 |
| GuardPosition | 128 → 133 | Target=(25,80)，Destination=null；do frame=156 | Alpha frame=160、Beta frame=162 均为 AREA_GUARD；后续从 (30,80) 移动到目标格 |
| GuardCurrent 新位置 | 213 → 218 | Target=(25,80)，Destination=null；do frame=240 | 锚点取新位置；随后两侧均在 (6528,20608,0)、AREA_GUARD、300 HP |

三条回执均为 observed_match/native_input_observed，三个任务按 operation_observed 结算并释放租约。GuardPosition 的实际移动与输入观测分开记录：目标格到达约 Alpha frame=212/Beta frame=214，最终三组采样精确世界坐标相同。上述 do Frame 可晚于读取帧，因为读到了尚未执行的排队事件；is_executed 和输入列表名称不能用于证明 applied。

两侧依次采样的 frame 通常差 1–3，不能以该差值或不同帧的 CRC 断言同步。当前通过的是同一受控命令在双实例中的限定效果一致性；未做逐帧 CRC、UDP/重传、弱网或断线重连验证。最后四组只读状态继续推进，最终两侧均可读取并无新增崩溃报告。用户无需手动准备本轮场景。

| 记录目录后缀 | 结果与改动 |
|---|---|
| 161733 | 首版两侧加载崩溃，尚未下令；异常 EIP=006F3F5E，写入 00746C2A。直接 Fetch_ID 虚调用改为 UniqueID 字段读取后恢复正常加载；记录保留 ABI 不兼容证据，不用编译通过替代调用约定验证 |
| 162922 | 正常加载；MapRect 将合法格 (30,80) 误判越界，DLL 明确拒绝。改为既有地图观测使用的 MapCoordBounds，并保持有效 Cell 检查 |
| 163459 / 163951 | DLL 接受输入，但受控 G 的格子进入 Destination，未符合 S2 的 Target 样本；判据保留 unverified，未自动重发。后者逐次读取确认任务可变化，并发现 out/do 的 Frame 重调度 |
| 164406 | 将已校验 Cell 传入 packed Target 参数后限定通过；修正既有事件签名并增加回归 |

首次导入脚本缺少项目根路径，在触碰游戏文件前失败；最终命令使用 `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 .agents/tmp/engine-build/guard_check.py`。首次加载失败后中断信号未找到脚本，实际由加载超时进入 finally 完成恢复；后续加入新崩溃报告立即退出的检查。除首轮真实崩溃外，其余退出均由脚本按验证结果主动停止，前后崩溃报告字节一致；切屏会影响帧推进，现有证据不支持将首轮崩溃归因于切屏。

所有完成的真机尝试均记录恢复成功：原 DLL/配置哈希匹配、DLL 原硬链接关系恢复、端口关闭、本轮进程停止。最终两侧仍使用原 DLL SHA-256=59b8d235a44398f20d290b44b60b92d7127fada1353cfe1d2bfd0a8b646a0b28。首轮生成的崩溃报告与日志作为诊断留证，后续未覆盖为旧报告；恢复范围为 DLL 和启动配置，不宣称日志未变化。

## 车辆多态补测：限定正例通过

本轮使用同一 Guard DLL 与既有双实例名册，未修改业务代码、DLL 源码、显示配置或 DSH。人工准备 CMIN、Engineer-FV 与受伤 Grizzly，接口动作仍经隔离测试技法 → Commander → MicroLayer → Executor；临时驱动为 .agents/tmp/engine-build/guard_polymorphism_check.py 与 guard_polymorphism.py。空 FV 对照按用户要求跳过，S2 空车原版对照仅作为已有背景，不等于本轮新接口空车实测。乘员条件依人工说明和 Engineer 的 limbo 状态关联，不能当作新增动态模式回读。

本轮限定范围汇总为 .agents/tmp/engine-build/backups/guard-poly-20261002-172006/scope-result.json，status=passed；原 validation.json、逐帧 polymorphism-observations.jsonl、技法与回执 polymorphism-decisions.jsonl、人工说明 human-observations.jsonl 及两份输入观测 state.bin 保留。原驱动第一段 FV 的标签仍为 empty_fv_guard，但该操作在执行前的 control.json 和人工记录中明确改为 Engineer-loaded FV；不得据原标签宣称空车接受了维修命令。原始 validation.json 的 failed 来自主执行者按用户缩小范围主动停止剩余矩阵，异常为 Human requested scenario stop，不代表下表接口或效果失败；scope-result.json 保留原记录引用、标签映射、实际范围、跳过项与恢复证据，不覆盖原日志。

| 操作 | 输入及对象 | 实际效果与人工观察 |
|---|---|---|
| CMIN GuardCurrent | native_id=1043865；依据 10698、观测 10701，do frame=10712；Area_Guard、Target=(46,76)、Destination=null；单次发送并释放租约 | 10703 帧 GUARD；10717 HARVEST；11575 ENTER；11606 UNLOAD；11621 资金 4600→5100；11635 再次 HARVEST。用户确认没有追加人工指令，矿车自行采矿并循环；不证明最近矿选择或无矿行为 |
| Engineer-FV GuardCurrent | native_id=1043908；依据 23661、观测 23664，do frame=23676；Area_Guard、Target=(43,74)、Destination=null；Engineer native_id=1043899 在准备时 in_limbo=True；单次发送并释放租约 | IFV 自行从 (43,74) 移到 (49,77)，伤车位于 (50,77)、native_id=1043820；HP 于 23749 / 23832 / 23915 / 23995 帧为 155 / 205 / 255 / 300，准备时为 105。用户目击成功；不承诺扫描半径、其他目标或永续护送 |

两条回执均为 observed_match/native_input_observed；后续采矿循环与增血由独立轨迹证明，不增强通用回执为 applied。背景配置为双实例，但本轮只采己方轨迹与当前玩家输入，没有配对 Beta 中 Alpha 对象的效果、同帧 CRC 或完整同步验证；不得沿用 Grizzly 结果扩展声称经济/维修双实例同步全部通过。两侧崩溃报告字节一致，原 DLL/配置哈希、DLL 硬链接关系、端口关闭与本轮进程停止均重新核对；测试已结束，原 DLL 已恢复。

首次记录 .agents/tmp/engine-build/backups/guard-poly-20261002-171204/validation.json：人工已准备车辆，矿车单独选中、GUARD、1000 HP；下令前两侧帧停在 Alpha 13236 / Beta 13247，临时驱动的 0.15 秒推进门拒绝，未建立 Commander 任务或发送 Guard 输入。该记录不构成矿车接口失败证据。脚本主动退出，两侧原 DLL/配置与硬链接恢复、端口关闭、进程停止，前后崩溃报告字节相同。用户报告切屏可能触发 Tab 对局信息界面，并说明日常联机中切屏可能造成全局短暂卡顿；本轮不能确定停帧原因，不能将此退出记为崩溃或持续暂停验证。

临时驱动已改为保留场景只读等待帧恢复，连续两次采样确认两侧推进后重新读取对象并发一次输入；停帧期间不下令，未知结果不重发。等待上限 20 分钟，到期进入 finally 恢复；效果观察仅累计两侧帧推进时的采样时间。完整己方对象从 state.objects 按归属跟踪，避免 observation.own 的 limbo 过滤将矿车瞬态误判为消失。方法经验：人工准备后优先保留可恢复场景，短暂卡顿不能作为接口失败；将阶段名称、实际载员条件与用户变更范围明确关联；允许按用户决定跳过价值较低的对照，原始日志和限定范围结果分别留存。此项修正只属于临时驱动，不代表生产 MCP 已修改或持续暂停测试已完成。

## 后续受控验证步骤

本轮临时替换已获用户确认并恢复；再次替换执行前按当轮范围告知并核对授权：对 D:/Games/ra2probe 与 D:/Games/ra2probe-b 的 DLL、spawn.ini 及既有 spawn.ini.render-bak 备份，经临时文件替换两侧 DLL并启动现有双实例配置。停止及恢复须进入 finally，保留 DLL 哈希、配置哈希与原硬链接关系，不改 DSH 或系统依赖。

1. 先只读确认两侧 stage、当前玩家、capability=1 和己方 native_id；与原版输入 whom ID 关联，检查读取稳定性与崩溃日志。
2. 通过临时内部测试技法向 Alpha 单个 Grizzly 下发 GuardCurrent、GuardPosition；记录请求、DLL 回应、当前玩家输入、双方对象 Mission/位置与帧。模型不得直接调用 engine client 下令。Beta 维持不操作。
3. 与 S2 原版输入和预期效果对照；GuardPosition 观察实际移动和到达，输入确认与任务效果分别记录。双实例验证不能用不同采样时刻的 frame 差代替同步判据。
4. 所有本轮进程与连接关闭，恢复原 DLL/配置并复核哈希、硬链接、端口和崩溃报告。后续仅按未测问题选择多态与拒绝场景，不要求执行全矩阵。

本轮 Grizzly 与 CMIN、Engineer-FV 的限定正例已收尾。下一步优先补服务端错误身份、归属、旧依据帧等受控拒绝边界，场景无需生产单位，可复用现有内部测试技法链并在测试传输适配层构造错误依据；生产校验不得放宽，不能直接开放原始下令工具。再按证据选择 S4 技法迁移，避免默认要求低价值全矩阵；上述拒绝分支仍未真机验证。对象护送、建筑保护、HARV 实测、动态载员回读、完整请求结果契约、长期任务和 S4–S6 未完成。持续暂停恢复未确认，S 不代表游戏暂停；Beta 的既有场景为 Americans，不假定苏军。完整 DSH idle/dispose 生命周期仍未验。
