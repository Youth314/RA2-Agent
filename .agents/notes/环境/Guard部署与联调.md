# Guard 部署与联调

日期：2026-10-02。当前状态：用户已明确确认长期替换并保留备份；DLL 已部署，独立复核通过。用户已关闭旧 DSH、重新启动普通 ra2 测试会话；[普通会话联调四项限定通过](../验证/GuardDSH联调验证.md)，本轮游戏与采集已结束、启动配置恢复复核通过。功能证据见[Guard 技法迁移验证](../验证/Guard技法迁移验证.md)，底层产物与未测边界见[Guard 接口验证](../验证/Guard接口验证.md)。

## 具体部署范围

目标仅为 D:\Games\ra2probe\libra2yrcpp.dll 和 D:\Games\ra2probe-b\libra2yrcpp.dll；两者当前互为硬链接。源产物为项目 .agents/tmp/engine-build/artifacts/guard-v1/libra2yrcpp.dll，部署前核对已验证 SHA-256 与 manifest，不重新下载或构建。本轮不修改 ra2yrcpp.json、显示设置、DSH 插件或系统依赖。

原 DLL、部署清单及源 manifest 保存到 D:\Games\ra2probe\.ra2-agent-backups\guard-v1-<时间>\，目录在项目 tmp 外，避免临时产物清理后失去回滚副本。替换采用独立暂存文件加 os.replace，不能直接覆盖原硬链接内容；Alpha 换入新 DLL 后，Beta 以原子替换重新链接 Alpha，核对两侧哈希与 samefile。成功后保留新 DLL，后续游戏启动加载它；备份不自动删除。

脚本为 .agents/tmp/engine-build/guard_deploy.py：check 用于原 DLL 状态的部署前预检，长期部署后改按持久清单核对当前指纹；apply 创建备份、替换、核验并写部署状态，异常时恢复原 DLL；rollback <deployment.json> 在游戏关闭且当前仍为预期新版时恢复原 DLL 与硬链接，拒绝覆盖未知版本。部署、回滚都拒绝现存游戏或开放探针，不主动结束用户对局。spawn.ini、spawn.ini.render-bak、ra2yrcpp.json 和崩溃报告只记哈希/存在性，本脚本不修改它们。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py check
# 仅在用户确认长期启用后执行：
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py apply
# 回退示例；替换为实际部署清单路径，游戏需关闭：
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py rollback /mnt/d/Games/ra2probe/.ra2-agent-backups/guard-v1-<时间>/deployment.json
```

如果临时脚本已被清理，仍可从持久备份回退：先关闭游戏并核对部署清单与备份 SHA-256，通过独立暂存文件换回 Alpha，再以 Alpha 为源原子换回 Beta 硬链接，复核两侧原哈希与 samefile。不得用未经核验的其他 DLL 或直接原位覆盖硬链接。

## 本次长期部署结果

持久清单：/mnt/d/Games/ra2probe/.ra2-agent-backups/guard-v1-20261002-214431/deployment.json，status=installed。原 DLL 在同目录 original-libra2yrcpp.dll，SHA-256=59b8d235a44398f20d290b44b60b92d7127fada1353cfe1d2bfd0a8b646a0b28；部署 DLL SHA-256=862a8c318a7193c5b4a6ec6899af26ecebef47b05b0270ce86debef6ef11010c。脚本核对后，独立再次复核两侧哈希、原备份哈希、DLL samefile 和清单所列配置/崩溃报告哈希，均通过。没有重装工具、修改 DLL 源码或游戏其他配置；此次授权后，新 DLL 长期保留。

本次回滚命令为下列命令；先关闭游戏，不自动终止用户对局。若清理过项目临时脚本，依照上节从持久清单和备份手工恢复。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py rollback /mnt/d/Games/ra2probe/.ra2-agent-backups/guard-v1-20261002-214431/deployment.json
```

本轮联调目录为 .agents/tmp/s4-dsh/run-20261002-214431/，capture.py 使用两个只读 Observer，保存 observations.jsonl、原版事件、新事件对应原始状态、阶段标记和 latest.json；独占写入者为 DSH 中的模型/自动层。启动前备份两側 spawn.ini/spawn.ini.render-bak 和诊断留证，退出 finally 恢复测试配置；不恢复已获长期启用授权的 DLL。首次 status 连接 GameSession 会启动既有自动层，可能展开 MCV、开始生产，不能将该入口称为完全无游戏动作；自动行为与显式 native_guard 按对象/原版事件分别归因。

## 当前宿主与最小联调

旧 DSH 与 MCP 已由用户关闭。重新启动的 DSH PID=185141（21:46:40）、默认 MCP PID=185173（21:46:45）；MCP cwd=/home/youthz/ra2-agent，PYTHONPATH=/home/youthz/ra2-agent/src，启动时间晚于 S4 提交。用户负责普通 ra2 会话的任务投递；未派玩家子 Agent，未启停 bundle 热换、强杀 MCP 或修改 preset。宿主加载约束见[指挥层](../设计/指挥层.md#挂载方式)。

已核对新 MCP 的启动时间、cwd、PYTHONPATH 并启动既有双实例名册；Alpha PID=25228、Beta PID=39028，两側 stage=2、guard_interface_version=1，max_connections=16 为此次配置回读值。通过正常 status/tactics/call/cancel 入口验证卡片和单次输入，用户已准备 CMIN，harvest/auto_harvest 接线、原生循环及限定窗口输入次数均完成检查，实际证据与限制见联调验证。测试采用独占指令写入者，其他连接只读；日志保存到项目忽略目录，不读取凭据或无关会话内容。

本轮不以完整模型策略评测、冷玩家唤醒、idle/dispose、持续暂停或完整联机同步为前置验收。原版输入确认与实际采矿效果分别记录；短暂切屏停帧等待恢复，未知结果不重发。本轮连接和归属游戏进程已关闭，四个启动配置恢复并独立复核，长期 DLL 保留，崩溃报告没有新增；结果见联调验证。
