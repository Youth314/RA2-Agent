# Guard DSH 联调验证

日期：2026-10-02。范围：S4 首组在普通 ra2 preset 共享 MCP 中的短任务接线；不验证玩家子 Agent 释放、冷唤醒或完整宿主生命周期。DLL 已经用户明确授权长期启用，指纹、持久备份与回滚见[部署记录](../环境/Guard部署与联调.md)；技法契约和已有回归见[迁移验证](Guard技法迁移验证.md)。

## 分工与取证

用户关闭旧 DSH、启动新普通 ra2 会话，并将短任务转交模型、复制回复回传。模型是本轮 Alpha 唯一显式指令写入者，动作只经技法；未派玩家子 Agent，Beta 不操作。主 agent 启停既有名册并以两个只读 Observer 记录状态、原版事件和阶段，不替模型下单位命令。MCP 首次连接后，其既有自动层独立执行 deploy_mcv/auto_opening，须与显式测试分开归因；普通 status 连接并非完全没有游戏行为。

本轮目录为 .agents/tmp/s4-dsh/run-20261002-214431/，capture.py/report.json 保存启动、备份、读取与恢复状态，phases.jsonl 标记任务窗口，observations.jsonl/latest.json 保存轨迹。本轮 D01–D04 已完成限定验证，采集和游戏已关闭，恢复结果见下节。DSH 模型原文由用户提供，不读取凭据或其他会话内容。

等待期间的协作约定见[能力验证方法](能力验证方法.md#6-最小实验与人工协作)；本轮向用户说明正在只读采集、检查轨迹、整理证据，独立检查完成时明确只等待回复，不追加命令。

## D01：一次当前位置警戒，限定通过

模型读取 native_guard 卡片，卡片帧=5979，具备 has_units/has_map/guard_v1 门；从合法 status 选择 Agent ID=224、Grizzly Battle Tank、cell=(30,80)。只调用 native_guard(units=[224],params={}) 一次，受理 intent_id=fba938f9ece1；随后 status frame=6087 报 satisfied、到位 1/损失 0/失败 0、在管 0，frame=6195/6239 无新结果且单位仍在原格 AREA_GUARD。模型完成后停手，没有重发或终止单位命令。

原版事件补证来自 DLL 自带的逐帧 record.pb.gz，在游戏运行中复制为 Alpha-D01-record.pb.gz；检查帧 5900–6500，去重后只有一个对应车辆输入：event_type=4、house_index=1、Mission=11、whom ID=1043819/RTTI=52、target cell=(30,80)、destination=null、Timing=348339566。该事件在录制 observation frame=6064–6075 中重复出现，事件 Frame=6076；相同 Timing 与载荷的重复观测不计重复下令，is_executed 标志也不提升为 applied。帧 5900/6000 为 GUARD，6087/6195/6239/6500 为 AREA_GUARD，HP=300、位置未变。

证据为 D01-result.json、D01-recording-evidence.json 和 Alpha-D01-native-*.bin；录制快照 SHA-256=f63331654bf24e75550646691c6bcf7ef92fad81498ffb9f9a8f3125c7506ae1。检查窗口证明一次原版输入、普通模型受理/结算与状态一致，不代表无限期警戒或完整联机同步；原生 input 不带请求 ID，与本次模型回报按席位、唯一操作者、对象和时间窗口关联。

模型报告的旁支包括自动展开 MCV、生产 Allied Power Plant，以及“挂了 mcp__ra2__* 工具的会话都在跑”的唤醒未送达告警。本项不以该告警验收唤醒，也不新增宿主改造。用户转交文本曾额外含派 subagent 的首句，模型按更具体的“不派玩家子 Agent”任务正文执行；实际结果属于普通会话，不能记成玩家子 Agent 通过。

## D02：一次地点警戒，限定通过

模型 status frame=27947 确认同一 Agent ID=224 在 cell=(30,80)，只调用 native_guard(units=[224],params={cell:[25,80]}) 一次，intent_id=8438d403bde2。frame=28101 报 satisfied、到位 1/损失 0/失败 0、在管 0，但单位当时在 cell=(28,80)；frame=28187 独立观察到 cell=(25,80)、AREA_GUARD、无新结果。输入结算先于实际抵达；两个 status 相隔 86 帧是采样间隔，不是精确的抵达耗时，逐帧抽样在 frame=28140 已记录目标格。模型未重发、不处理旁支的待放置 Allied Power Plant，到达观察后停手。

检查逐帧录制 frame=27900–28400，只有一个对应车辆 AREA_GUARD 输入：house_index=1、whom ID=1043819/RTTI=52、target cell=(25,80)、Timing=348844589；observation frame=28057–28071 共出现 15 次，由 out 进入 do 时事件 Frame 变化，按 Timing 与载荷去重为一次输入。实时 Observer 在 frame=28071 也捕获同一 do 事件。证据为 D02-result.json、D02-recording-evidence.json 和 Alpha-D02-native-*.bin；录制快照 SHA-256=6f2f8040081f7f147a284472794f31b1a4490e61315af17ee2860068bc27bef7。限定场景证明普通 DSH 地点输入、输入任务结算与后续原生寻路分别成立，不承诺任意地点必达或持续守护。

## D03：显式 harvest 接线，限定通过

模型 frame=65147 选择唯一正在 HARVEST 的 Chrono Miner，Agent ID=238、native_id=1043952、cell=(47,63)。frame=65255 读取 harvest 卡片，按 v1 CMIN 一次 G、其他路径兼容移动及输入/效果分离的现有承诺，只调用 harvest(units=[238],params={}) 一次，intent_id=c668296c9a4f。frame=65409 回报 satisfied、到位 1/损失 0/失败 0、在管 0、cell=(48,64)/HARVEST；frame=65581 无新结果、cell=(48,65)/HARVEST，随后停手。

逐帧窗口 65100–66000 只有一个对应 CMIN 的 AREA_GUARD 输入，house_index=1、whom ID=1043952/RTTI=52、target cell=(48,64)、Timing=349708219；observation frame=65365–65379 共 15 次同一 out/do 输入观测。录制快照 SHA-256=206d426ffa6a93082dbab3c786c36ae80a06792fe0291c442c34090a2a95884a，证据为 D03-result.json/D03-recording-evidence.json；后续出现 ENTER、UNLOAD 和继续 HARVEST，状态与显式任务回报一致。普通 MCP 未启用 --log，本轮不宣称已有完整决策 JSONL；以用户回传的任务原文与既有逐帧录制交叉取证，不为单项测试重启宿主。

矿车下令前已经采矿，自动层保持启用；本项证明正式 harvest 的对象选择、一次原版 G 接线和任务释放，不独立证明由停工恢复。模型不能从 status 自行读取原版事件，真实 G 由主 agent 的只读取证补证；既有采矿状态和坐标变化不得单独归因于本次输入。恢复测试由 D04 单独验证。

## D04：停车后的自动恢复，限定通过

模型 frame=68334 确认同一 Chrono Miner 为唯一矿车，读取 hold_position 卡片，只调用 hold_position(units=[238],params={}) 一次，intent_id=595df37bc253。frame=68478 回报该任务 satisfied、到位 1/损失 0/失败 0、在管 0，矿车 cell=(35,75)、空闲；frame=68587 观察 cell=(34,75)、HARVEST、无新结果，在两次观察后停手。模型没有调用 harvest/native_guard，没有重复停车或 cancel；status 未显示 auto_harvest 项，不能由可见任务缺席断言自动层未执行。

逐帧窗口 68300–70000 恢复出两个不同输入：一次 Mission=STOP(13)，Timing=349779789，observation frame=68444–68455，event Frame=68456；随后一次 Mission=AREA_GUARD(11)，Timing=349781150，target cell=(35,75)，observation frame=68501–68515，do event Frame=68516。两者 house_index=1、whom ID=1043952/RTTI=52；分别重复观测 12/15 次，去重后各一次。Guard 排队观察晚于模型 frame=68478 的停车任务结算与租约释放；原版事件补证表明存在新的 G 输入，而非仅由继续采矿状态推断恢复路径。在用户停止额外操作、唯一模型仅提交停车和已审查的自动实现条件下，证据支持归因于 auto_harvest；原版事件无请求 ID，未额外挂载内部 dispatch 日志，不推广为完整因果跟踪机制。

独立采集 frame=68491 为 STOP、68565 为 HARVEST；69402 为 ENTER、69455 为 UNLOAD、69483 为 HARVEST，资金由 11200 增至 11700。frame=68300–70000 没有第二次 G，窗口覆盖恢复后的一轮进厂、卸货与再次采矿；限定证明自动恢复接线及不逐拍打断当前循环。没有通过反复停车单独实测 600 帧冷却和全部租约竞争分支，这些分支仍以已有离线回归为证据。模型未观察到 AREA_GUARD 中间态不构成失败，CMIN 可迅速切换为原生采矿任务，输入和实际效果分别留证。

证据为 D04-result.json、D04-recording-evidence.json、Alpha-D04-native-*.bin 与 observations.jsonl；录制快照 SHA-256=9baafe76df5c0c2f43098c7c407021c8945a28760d4b51590aa2e0a7b8b8d9c3。综合结果见 results.json，四项均为 passed_limited。

## 收尾与恢复

写入 STOP 后 capture.py 正常退出，report.status=capture_stopped，连接关闭、本轮 Alpha/Beta 游戏进程停止，spawn.ini 与 spawn.ini.render-bak 的四个文件存在性/哈希恢复，长期部署 Guard DLL 和两侧硬链接保留。独立复核四个配置、两个目录的 EXCEPT_CNCNET.TXT/except.txt、DLL 指纹与 samefile、原备份哈希、持久 deployment.status=installed、14521/14522 端口关闭及归属游戏进程消失，全部通过，证据为 independent-cleanup-check.json。没有新增崩溃报告，游戏日志与内建录制按正常运行更新；不宣称诊断文件从未写入。

DSH 及其 MCP 由用户管理，本轮没有再次重启或修改插件/preset；退出游戏不等于已经验证该宿主的 dispose 或下一局冷恢复。下一局先核对会话、连接与帧，不用重发本轮已结算任务。

## 采样经验

两个 Observer 顺序读取并间隔 0.5 秒适合状态/效果轨迹，但可能错过只存在数帧的 out/do 输入队列；D01 独立实时采集没有捕获 MegaMission，不能以此判命令失败或断言没有重发。现有 DLL 的逐帧录制已有事件字段，优先从已存在录制恢复短输入，不必立即修改生产代码、提高所有采样频率或重复下令。

recover_native.py 只读复制当前压缩录制，逐块解压长度前缀 GameState，限定帧窗解析；容许运行中 gzip 尾部未封口和最后一条记录不完整，只有完整记录用于证据，记录快照哈希与实际扫描末帧。后续读取新的帧窗可复用脚本，不改变已有快照、游戏设置或真实命令。恢复出来的原版输入、模型任务结算和实际效果分别记载。

## 后续任务与限制

S4 首组已完成 native_guard 两种输入与 CMIN 显式/自动采矿的普通 DSH 限定接线验证。没有增加生产代码或重复无关测试；本轮不重复已取消的 HARV 或新接口空 FV 对照。剩余迁移与后续顺序见[演进计划](../设计/L1基础能力与技法演进计划.md)，不由本轮四项短任务升级为完整 S4/S5/S6 或整套宿主验收。

持续暂停恢复、完整 DSH idle/dispose、玩家子 Agent 冷恢复、完整联机同步、动态载员、对象护送与长期可靠性仍未验证。Beta 为 Americans，切屏短暂全局停帧只读等待，不直接当接口失败；S 是停止单位动作而非暂停游戏。
