# Attack 玩家接口验证

日期：2026-10-03。范围见[功能组方案](../../drafts/接口/U08受控Attack功能组方案.md)。用户已确认协议、Python、DLL 源码和一次项目内独立构建；用户后续已确认双侧临时部署、同局 MTNK→AMCV/GACNST 两次技法攻击、人工及时 D 窗口、起局与统一收尾，并补充确认完整 Beta 建造/放置、一台 MTNK 与必要普通移动；不包含配置修改、长期启用或目标 ID fault 注入。实现提交为 3946ba6，离线检查、独立 DLL 构建及 PE 检查通过；编译不证明玩家效果或联机同步。

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

Attack v1 双侧临时部署及 Attack/Target v1 加载通过，恢复批次 MTNK → AMCV 的新攻击输入/实际 Target 双证据限定通过；独立 DSH 建筑批次 MTNK → GACNST 双证据、真实 Beta 的受理 / satisfied / operation_observed / 租约释放限定通过，见下节。各批已恢复 Stop v1。原生服务端目标 ID 不匹配拒绝、非空目标中的及时展开均未完成。既有人工 MTNK → AMCV 非空 Target 证据只在[U08 验证](U08实际目标回读验证.md)维护，不证明新 DLL 请求可靠。操作批次见[集中真机操作单](../../drafts/接口/Attack集中真机操作单.md)，已结束批次的授权不延续到新实验。

其他型号与武器、步兵/飞机目标、盟友/中立目标、FogOfWar=Yes、Cell/ForceFire、请求去重、跨局身份、完整 DSH 生命周期及完整联机同步不属于已验证支持。长期游戏 DLL 基线仍为 Stop v1，具体环境事实见[Stop 部署](../环境/Stop部署与对照.md)。

## 首轮集中批次结果与后续准备

已授权批次于 2026-10-03 17:13 起局，两侧 stage=2、attack_interface_version=1、target_observation_version=1，max_connections=16。真实 Beta 玩家通道由用户转交 DSH 主持会话；用户转述 Beta 的电厂待放置、电力 0/0，后续 GAPILE / GAREFN / GAWEAP 与 MTNK 生产准备不在原两次攻击授权内。采集仅出现 Alpha 的 AMCV、Beta 的 AMCV / GACNST，无 MTNK、无采到的 MegaMission；A1–A4 未执行，不作攻击效果、卡片调用或完整 DSH 生命周期结论。既有 Beta 自动开局与两次显式攻击范围分开记录，不能把待放置状态解释为 Attack 实现失败。

本轮固定 900 秒采集等待耗于准备，不能在前置对象未就绪时用相同短期限驱动下一轮。下一批须先明确准备动作的授权边界，准备完成后再进入短攻击验证窗口；准备状态低频读取，不以高频采集等待生产。具体候选授权及准备要求见集中操作单，尚未确认，不能据建议提前下令或重开局。

本轮于 17:29:03 收尾，按本轮 PID / executable path / creation time 关闭 Alpha 27668 与 Beta 41800；独立复核无 gamemd、14521/14522 无监听，双侧恢复 Stop SHA-256=cf7bab758ea29152c032c83f2b3adf9b5b3d849a0bf1326c16313ea7226a5978 且 samefile=True，十项配置/崩溃报告指纹一致。临时清单 D:\Games\ra2probe\.ra2-agent-backups\attack-v1-20261003-171311\deployment.json 为 rolled_back，长期 Stop installed 清单保持 installed，无 cleanup_errors。生命周期收尾通过不等于 Attack A1–A4 通过。

本轮生命周期报告与采集位于 .agents/tmp/attack-live/run-20261003-171304/，两侧各 7827 个样本；原生录像在终止 PID 前复制，gzip 尾部完整性未核验。已通过的离线 81 项、PE / 构建及本轮新版本加载检查不因准备范围调整而重跑；下次只核对本次进程所需前置，不增加旧 Stop / 空 Target 对照。仓库根既有 package-lock.json 保留，不作为本轮改动。

## 恢复批次结果与证据

用户回复“好的，请开始”，确认同一 Attack DLL 临时部署、原配置重新起局、Beta 模型通过现有生产/放置技法补齐 GAPOWR / GAPILE / GAREFN / GAWEAP、只生产一台 MTNK、必要普通移动、原两次受控攻击/人工 D 与统一恢复 Stop；不含 fault、长期部署、配置或无关生产。现有和已在队列的对象复用，unknown 先回读，不重发。真实 Beta 通道由用户转交 DSH，Beta 自读确认 MTNK Agent ID=220、可见 AMCV Agent ID=212，健康未在它的 MCP status 单位行提供，主持侧合法只读健康另记。Beta 报告未发移动指令，受试车移至 (40,81) 的来源未确认，不归因于 automatic；该项不作为本次新攻击输入。

本批 run-20261003-174058 双侧临时部署与新局前置通过，使用原配置；准备阶段每 5 秒读取，未启动短攻击计时。低频增量观测未及时取得目标格探索信息，新鲜只读 bootstrap 已确认目标合法可见且命令身份提供；故短采集使用同轮新鲜地图建立的 capture-verification，而非用低频缓存缺席否认玩家可见性。准备就绪与攻击前 AMCV 健康为 935，偏离操作单的满血 1000，MTNK 健康 300、当前实际 Target=none，目标在射程外；按 935 记本轮基线，不重起局补满血。Beta 再次自读确认对象后，用户转交 A1 开始指令并确认执行；主持未下单位命令。

A1 新输入/实际 Target 双证据限定通过：采到唯一 MegaMission event_type=4、Mission_Attack=1、house_index=0、timing=421007657，actor native ID=1043934 / RTTI=52、target native ID=1043808 / RTTI=52，destination / follow 的 RTTI 均为 0、is_planning_event=false。首次采样 frame=56654，该输入仅见于 Beta，out/do 三次采样属于同一输入，不作三次下令或完整联机同步结论；is_executed 和事件 frame 不单独证明执行。此前短采集不存在本输入，首次匹配实际 Target 在 frame=56670，此前为 none；其后到 frame=57534 共 169 项非空目标样本匹配原 AMCV，公开投影为 object / Agent ID=212。单写入者与窗口关联仍是证据限制；真实 Beta 已有记录由用户转回：下令前 frame=56584，受理 attack_target#67a9058eba7c，唯一一次回读 frame=56690 显示 satisfied / 到位 1 / 损失 0 / 失败 0 / 在管 0 项；没有 unknown、补发或 cancel。薄技法受理、结算及租约释放限定通过；模型面没有 completion_basis / observations 字段，不把它们写成 Beta 实读值。

另行记录 AMCV 健康从 935 按 65 递减至 25 的效果，不能将一次输入确认等同于永久接战。frame=56873 首次采到健康 675，距首次匹配 Target 约 4.51 秒；聊天多轮提示无法可靠赶上健康 ≥700 的人工 D 窗口。短采集没有 GACNST 样本，A2/A3 未完成、A4 未执行，不发第二次攻击或重起局补尾窗。随后采集触发 Alpha match boundary；边界检查在写出该帧前终止，不能仅凭异常文本认定具体胜负标志、击毁或崩溃原因。记录与原生录像保留，gzip 尾部完整性未核验。

本轮 18:03:17 按 Alpha PID=26356 / Beta PID=34112、executable path 与 creation time 收尾。双侧 DLL 恢复 Stop SHA-256=cf7bab758ea29152c032c83f2b3adf9b5b3d849a0bf1326c16313ea7226a5978、samefile=True；独立复核无 gamemd、14521/14522 无监听、十项配置/崩溃报告指纹一致。临时清单 D:\Games\ra2probe\.ra2-agent-backups\attack-v1-20261003-174105\deployment.json 为 rolled_back，长期 Stop 清单仍 installed，rollback_passed=True、cleanup_errors=[]。父流程 status=failed / passed=False 来自采集的对局边界，必须与回滚成功和限定 A1 证据分开，不能改写为整批通过。

生命周期与证据位于 .agents/tmp/attack-live/run-20261003-174058/，a1-evidence.json 汇总输入、Target 与健康序列；capture-verification 两侧各 1154 项高频样本，frame 范围 Alpha 51584–57538、Beta 51582–57534，低频准备两侧各 255 项仅刷新 latest。81 项离线、构建 / PE、旧 Stop / 空 Target 对照均未重跑。用户指出网络不适合实时协调；未来若另获补测授权，采用提前下达的本机连续操作单、玩家直接看游戏画面判断 D 时机与事后读记录，不再经主持聊天提示抢秒级窗口。未完成的展开 / 建筑分支不作为其他离线功能组开发的前置。

## 使用方显示缺口与后续范围

原真机版本的离线代码核查：AttackTarget 在 runtime/intents.py 注册 kind=attack_target；MicroLayer._advance 的 ENGAGING 分支仅匹配旧 kind=attack，新切片走 operation_observed 并由 _finish 保存 completion_basis / receipts / observations。原真机版本 command.py 的新结果文本仅渲染状态、计数、原因与 unknown 提示，省略上述依据；原单位行也省略 health。故 Beta 报告依据/血量“未提供”符合当前工具输出，不能解释成新请求走了旧攻击分支。该代码核查复用既有离线证据，不作为本局隐藏字段的实际读数。

用户转述的 placement_ready 早期误报与 frame 约 16301 的标识表静默重建按独立调查保留，不据此认定该局 ID 变化的具体原因。后续玩家输出及重连修复分别见[玩家状态输出验证](玩家状态输出验证.md)、[会话重建验证](会话重建与身份验证.md)，不改变本页旧真机版本的读数。未验展开不要求先补完，网络抢时序不作为默认流程。

## 独立 DSH 建筑批次与报告复核

2026-10-03，用户委派的测试协调者完成一次 MTNK → 合法可见 GACNST 的 attack_target，并授权临时部署既有 Attack DLL、原配置起局、真人与真实 Beta 准备、单次攻击、短只读采集和恢复 Stop；不包含非空 AMCV 展开、fault、配置修改或长期部署。报告为 .agents/tmp/attack-gacnst/BATCH-REPORT.md，原始证据为 capture/prep-run/observations.jsonl、raw/ 和 report.json。本次开发复核只读取这些已有记录及 DLL，不重跑游戏、加载或已有离线测试。

真实 Beta 由 play_as_beta 创建，报告记录 child=37682908-e992-459e-8845-bdea6dd61a16，MCP 使用 --roster config/match.json --player Beta。请求的玩家 ID 为 units=[219]、target=223；采集侧 MTNK Agent ID=221 / native ID=1043915，目标 GACNST 在 Alpha 采集侧 Agent ID=225 / native ID=1044520 / object_type=6。玩家与采集身份空间分别维护，不能交叉使用 Agent ID。

原始记录复核：此前采集侧 MTNK 实际 Target 为 none；唯一新攻击输入 timing=423080040，actor native ID=1043915 / RTTI=52、target native ID=1044520 / RTTI=52。首次采样 frame=21339、source=out，事件自身 frame=21336；后续 do 两次采样为 21344 / 21349，事件自身 frame=21352，三条记录属于同一个输入。实际 Target 在采样 frame=21354 变为 native ID=1044520 / object_type=6，保持到窗口结束。事件 frame、Mission 与 is_executed 不单独作执行判据。

合法性与结算仅按报告转述的真实 Beta 工具输出登记：可见敌方 GACNST #223、health=1000；受理 attack_target#0479be853364 一次，结果 satisfied / 到位 1 / 损失 0 / 失败 0，在管 0 项；219=operation_observed，最近回执 observed_match/native_input_and_target_observed（21354），observations 为 native_input=observed（21351）、actual_target=state_changed（21354）、target_status=object。采集侧底图未刷新，公开 Target 为 unobservable，故合法公开目标证明来自 Beta 工具转述，采集仅提供原生身份和帧序旁证；未取得采集侧 object 投影的独立证明。无 unknown、重发或 attack cancel；本批没有执行 cancel，不登记为新的 cancel / Stop 对照。目标健康保持 1000，不宣称开火、掉血、击毁或持续接战。

附带 attack-evidence.json 误以玩家 Agent ID=219 查询采集侧对象，读到 Chrono Miner；其 actual_target_sample_count 也将 status=none 的非空字典计入，不能用于 Target 判定。开发复核改按 diagnostic_own.native_id=1043915 对齐原始行，得到上述 none → 1044520 序列；保留原报告和提取文件，不覆盖原始产物。报告中的“out 首采 21336 / do 回声 21352”均是事件自身帧，本页以采样帧明确修正。

版本限制：起局 revision=ad48163，批中主开发并行修改 command.py 与相关测试；DLL 和 Attack 判定未变，但玩家 Python 输出版本未冻结。健康 / 实际目标 / 依据文本按报告实读记载，不归因于 f854bf5 的固定运行版本，也不作为该提交的完整 DSH 回归。主持侧旧 MCP 进程发生 AttackTarget 导入错误，协调者未重启或接管；本批只读采集替代主持工具，不证明旧进程问题已解决。后续测试必须固定源码工作区和 MCP 版本。

收尾 report.json 为 capture_stopped、两侧各 326 项、connections_closed=true。报告按本批 Alpha PID=26964 / Beta PID=29548 及 executable path 停止，报告复核无 gamemd、14521/14522 无监听；未记录 creation time 核验，不补写该项。持久清单 D:\Games\ra2probe\.ra2-agent-backups\attack-v1-20261003-182826\deployment.json 为 rolled_back，restored_hardlinked=true、unchanged_after_rollback=true，十项配置/崩溃文件指纹一致；长期 Stop 清单保持 installed。开发只读复核两侧当前 DLL SHA-256=cf7bab758ea29152c032c83f2b3adf9b5b3d849a0bf1326c16313ea7226a5978，samefile=true；Windows 只读复核当前无 gamemd 进程、14521/14522 无监听，十项配置/崩溃文件指纹仍与部署前一致。录像在停 PID 前复制，gzip 尾部未验证。归档为普通 MTNK → GACNST 的限定正例，未验展开、其他目标/型号、跨局与完整联机同步继续保留。
