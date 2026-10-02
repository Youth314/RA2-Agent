# Stop 部署与对照

更新日期：2026-10-03。状态：用户已明确确认长期启用；两侧已由 Guard v1 替换为 Stop v1，独立复核通过，运行加载检查待用户重启 DSH 并启动新局。实现与产物指纹在[Stop 玩家接口验证](../验证/Stop玩家接口验证.md)维护；被替换的 Guard v1 长期部署及旧备份见[Guard 部署](Guard部署与联调.md)。

## 环境范围与回滚

拟临时替换 D:\Games\ra2probe\libra2yrcpp.dll 与 D:\Games\ra2probe-b\libra2yrcpp.dll，保留两侧硬链接关系；源为项目 .agents/tmp/engine-build/artifacts/stop-v1/libra2yrcpp.dll。替换会增加 Stop/Idle 入口和 Idle 对象回读，保留 Guard v1；未经真机验证，不能视为长期部署。源与当前两侧文件指纹、PE 架构、构建 manifest 已核验，当前 DLL 仍为 Guard v1。

部署脚本 .agents/tmp/engine-build/stop_deploy.py 复用 Guard 部署流程：拒绝现存游戏/开放端口与未知 DLL；先将当前 Guard DLL 和清单持久备份到 D:\Games\ra2probe\.ra2-agent-backups\stop-v1-<时间>\，再独立暂存、原子替换 Alpha、重新链接 Beta、核对哈希与 samefile。不会覆盖既有 Guard 部署备份；失败时恢复当前 Guard。测试结束关闭本次实例后执行 rollback 恢复当前 Guard，保留备份；本次请求不是长期替换授权。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/stop_deploy.py check
# 以下操作必须在本次确认后执行：
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/stop_deploy.py apply
# 用 apply 输出的实际 deployment.json：
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/stop_deploy.py rollback <deployment.json>
```

拟使用现有 config/match.json 双实例名册；.agents/tmp/a1-stop/capture.py 从既有采集脚本调整，仅在新 DLL 已部署、没有现存对局时启动。它会先备份两侧 spawn.ini / spawn.ini.render-bak，再按名册临时生成启动配置，启动本次实例并只读采集，结束时关闭归属本次的实例、恢复四个启动配置及原硬链接关系。游戏会自行写 ra2yrcpp.log / record.pb.gz 等运行日志；实验留证写 .agents/tmp/a1-stop/。不改显示设置、ra2yrcpp.json、DSH 插件/preset 或系统依赖。

预检时没有 gamemd 进程，14521/14522 关闭；现存旧 MCP PID=185173，不重启、不接管。实验时用户应关闭普通 DSH 游戏会话或保证其不调用游戏工具，以防自动层介入；测试脚本使用独立只含 stop 的注册表与正常 Commander/Micro 链，没有自动技法。真正执行前重新检查现场，不能把本记录当实时状态。

## 人工步骤与等待期间工作

1. 获确认后由 Agent 临时部署、启动并确认两侧 stage=2、帧推进及 Guard/Stop 版本，再告知可操作；用户不必提前启动新局。
2. 用户在 Alpha 选一台 Grizzly Battle Tank，命令其前往较远空地，在尚未到达时按一次 S，确认途中停下并告知“人工 S 完成”；避免同时 G、重复 S 或其他单位操作。Agent 在此期间持续只读采集、关联该 actor 的 Idle 和轨迹，准备同对象接口对照。
3. Agent 按观测确认 native ID，启动 .agents/tmp/a1-stop/stop_call.py --native-id <ID> --moving --label moving；脚本只等待单位进入 MOVE 且帧推进。Agent 告知已就绪后，用户让同台车辆向另一处远空地移动，此次不按 S；脚本经正式 stop 技法下达一次输入。Agent 同时核对输入、原目的地、位置变化和另一侧可见效果，用户只需观察是否途中停止。
4. 单位静止后，Agent 用同脚本 --label stationary 经正式技法再提交一次，验证既有 GUARD/STOP 不冒充新输入；用户不需额外按键。通过判据为新 Idle actor 匹配，移动阶段在原目的地前停止；静止阶段出现另一输入但不承诺长期不动。若低频采样漏事件，按已有逐帧录制补证，不重复发令制造“成功”。
5. Agent 收尾留证、停止采集（创建 .agents/tmp/a1-stop/STOP）、关闭本次游戏、复核配置恢复、回滚到 Guard DLL及两侧硬链接、检查崩溃报告并更新验证记录。新 DLL 保留在项目构建目录，不能自动长期启用。

采集与薄技法脚本已用于本次三项限定真机对照，结果见验证记录；人工操作期间持续只读采集并核对证据。需要保持前台时会明确提示；切屏导致短暂停帧先等待恢复，不直接判接口失败，不盲重发未知请求。

## 执行与恢复结果

持久清单为 /mnt/d/Games/ra2probe/.ra2-agent-backups/stop-v1-20261002-231826/deployment.json，当前 status=rolled_back，原 Guard 备份保留。临时部署哈希/硬链接核对通过；本次 Alpha PID=32944、Beta PID=24044，双侧 Guard/Stop v1 加载、帧推进及三项限定对照通过。采集 session=83307、移动调用 session=64028、静止调用 session=89559 均正常退出，不能复用为活动 session。

report.status=capture_stopped；本次游戏进程已关闭、14521/14522 关闭，四个启动配置恢复。独立再次核对配置哈希、四份既有崩溃报告、两侧 Guard SHA-256 与 samefile、持久备份及 rolled_back 状态，全部通过。两侧逐帧录制已保存到项目实验目录。当前长期启用仍为 Guard，新 Stop 构建产物保留但未长期启用；DSH/MCP 由用户管理，不据此声称已重启或关闭。

## 拒绝补测执行与恢复

用户已明确确认本次临时部署和拒绝测试。复用同一 Stop 构建产物；两次运行各使用独立持久备份，不重建或下载依赖。首轮目录 .agents/tmp/a1-stop-rejections/ 执行 12 项与两次合法对照；因 gzip 尾段未落盘，仅在 .agents/tmp/a1-stop-rejections-tail/ 补跑 foreign_actor、infantry_actor 与前后正例。完整证据范围见[Stop 验证](../验证/Stop玩家接口验证.md#服务端拒绝补测结果)，没有重复前 10 项。

首轮清单 /mnt/d/Games/ra2probe/.ra2-agent-backups/stop-v1-20261002-233824/deployment.json，Alpha/Beta PID=39420/36692；补测清单 /mnt/d/Games/ra2probe/.ra2-agent-backups/stop-v1-20261002-234243/deployment.json，PID=45040/31428。两个清单当前均为 rolled_back，Guard 备份保留；run.py 两轮 report.status 均为 passed，启动配置恢复、本次进程关闭、端口关闭。两个 exec session=23269/30458 均结束，不作为活动进程使用。

补测停止前核对末尾正例窗口终点 573，两侧已落盘录制分别到 Alpha 633/Beta 641；保存后再关闭游戏。脚本导入 tests 需要仓库根目录，执行命令为 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. python3 <run.py>；首次缺少根目录导入失败发生于游戏与启动配置修改前。

独立复核两个运行的四个启动配置、所有原配置/崩溃报告、持久 Guard 备份、两侧 Guard DLL 指纹与 samefile、rolled_back 清单通过；最终只读 preflight 再确认无游戏和开放探针，源 Stop 产物未变。DSH/MCP 未接管。本批不需要人工按键，模型动作仍经正式 stop 技法；固定错误由开发测试传输层注入。当前长期启用保持 Guard，Stop 未长期部署，后续环境调整按具体范围说明。

## 长期启用执行结果

用户已明确确认长期启用范围，本页 apply 流程已执行；范围仅为两侧 DLL 替换与持久备份，复用已通过三项 Grizzly 正例及 12 项限定拒绝的同一产物，不重建、不下载。预检与替换前各做一次只读检查：无 gamemd 进程、无开放探针端口、两侧 Guard v1 指纹与硬链接均符合预期。

替换的两个目标为 D:\Games\ra2probe\libra2yrcpp.dll 与 D:\Games\ra2probe-b\libra2yrcpp.dll，安装后 SHA-256=cf7bab758ea29152c032c83f2b3adf9b5b3d849a0bf1326c16313ea7226a5978、8249061 字节，两侧 samefile=true、链接数 2，硬链接关系保留。源产物指纹未变。

新增持久清单 /mnt/d/Games/ra2probe/.ra2-agent-backups/stop-v1-20261003-001402/deployment.json，status=installed；同目录 original-libra2yrcpp.dll 是替换前 Guard v1 副本，SHA-256=862a8c318a7193c5b4a6ec6899af26ecebef47b05b0270ce86debef6ef11010c。记录同时保存目标、源、前后哈希、硬链接标记、构建 manifest 及 10 个未变文件的替换前后指纹；不存在文件记 null。替换前后复核两侧四个启动配置、ra2yrcpp.json 与两份崩溃报告指纹一致，四个既有备份目录未改动。安装成功保留新 DLL，不做临时测试式自动回滚。

未改动：spawn.ini、spawn.ini.render-bak、ra2yrcpp.json、EXCEPT_CNCNET.TXT、except.txt、DSH 插件/preset、系统依赖；未自动启动对局，未接管 DSH/MCP。替换只保证文件落盘，不保证已加载或 DSH 生命周期通过；本次未运行部署脚本的自动化测试，仓库既有测试不覆盖该一次性脚本。

回滚路径：标准 rollback 子命令硬编码校验 original_sha256 等于 Guard v1 指纹，长期部署后按该子命令会拒绝执行；回滚须在以实际清单为参数前先由修改后的脚本处理，或先确认无活动游戏，再把 deployment.json 的 backup 路径复制回两个目标并重建硬链接。改善该脚本属于后续独立改动，不混入本次部署。

## 运行加载检查（已通过）

用户已授权 Agent 直接启动对局，未改任何配置文件。启动复用现有 config/match.json 名册与两侧既有 spawn.ini，只经 MatchHost.launch 起两个 gamemd；起局前拒绝现存 gamemd 与开放探针端口，起局前后核对 10 个配置/崩溃报告文件指纹完全一致。就绪探针走 Client 直连读一帧，不经过 MCP 的 GameSession，故本局没有由该入口建立自动层。

Alpha PID=9228、Beta PID=20056，两側 stage=2；只读回读 guard_interface_version=1、stop_interface_version=1，证明新 DLL 已在对局中加载并被解析。MATCH 模式下 stop 卡片显示、halt 隐藏。证据 .agents/tmp/a1-stop-load/launch-20261003-003905.json；脚本 load_check_readonly.py 与 launch_match.py 同为该目录的一次性脚本，不入库。

通过范围仅限「新 DLL 已加载且两种能力版本可读」，不等于完整 DSH 生命周期验收，也不代表用户的 DSH 会话已切到新局；完整 DSH idle/dispose、跨局身份与建筑/变身等动态 Stop 仍未验。

该局随后用于 A1 的 U02 姿态调查（见[U02 移动模式在线对照](../验证/U02移动模式在线对照.md)），结束后按用户要求关闭：Alpha PID=9228、Beta PID=20056 只按 PID 停止，两側探针端口关闭、无 gamemd 残留，10 个配置/崩溃报告文件指纹与起局前一致。

检查完成后推进 A1 的 U02 移动模式确认与 U08 实际目标回读调查；两类实验都需要对局内显式游戏动作，属新的动作范围，执行前单独说明并确认。
