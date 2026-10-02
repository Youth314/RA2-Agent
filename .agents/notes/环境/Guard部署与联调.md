# Guard 部署与联调

日期：2026-10-02。当前状态：部署方案与一次性脚本已准备，只读预检通过；长期启用与当前 DSH 重启尚待用户确认，未替换文件或重启服务。功能证据见[Guard 技法迁移验证](../验证/Guard技法迁移验证.md)，底层产物与未测边界见[Guard 接口验证](../验证/Guard接口验证.md)。

## 具体部署范围

目标仅为 D:\Games\ra2probe\libra2yrcpp.dll 和 D:\Games\ra2probe-b\libra2yrcpp.dll；两者当前互为硬链接。源产物为项目 .agents/tmp/engine-build/artifacts/guard-v1/libra2yrcpp.dll，部署前核对已验证 SHA-256 与 manifest，不重新下载或构建。本轮不修改 ra2yrcpp.json、显示设置、DSH 插件或系统依赖。

原 DLL、部署清单及源 manifest 保存到 D:\Games\ra2probe\.ra2-agent-backups\guard-v1-<时间>\，目录在项目 tmp 外，避免临时产物清理后失去回滚副本。替换采用独立暂存文件加 os.replace，不能直接覆盖原硬链接内容；Alpha 换入新 DLL 后，Beta 以原子替换重新链接 Alpha，核对两侧哈希与 samefile。成功后保留新 DLL，后续游戏启动加载它；备份不自动删除。

脚本为 .agents/tmp/engine-build/guard_deploy.py：check 仅查产物、现有文件、游戏进程与端口；apply 创建备份、替换、核验并写部署状态，异常时恢复原 DLL；rollback <deployment.json> 在游戏关闭且当前仍为预期新版时恢复原 DLL 与硬链接，拒绝覆盖未知版本。部署、回滚都拒绝现存游戏或开放探针，不主动结束用户对局。spawn.ini、spawn.ini.render-bak、ra2yrcpp.json 和崩溃报告只记哈希/存在性，本脚本不修改它们。

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py check
# 仅在用户确认长期启用后执行：
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py apply
# 回退示例；替换为实际部署清单路径，游戏需关闭：
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 .agents/tmp/engine-build/guard_deploy.py rollback /mnt/d/Games/ra2probe/.ra2-agent-backups/guard-v1-<时间>/deployment.json
```

如果临时脚本已被清理，仍可从持久备份回退：先关闭游戏并核对部署清单与备份 SHA-256，通过独立暂存文件换回 Alpha，再以 Alpha 为源原子换回 Beta 硬链接，复核两侧原哈希与 samefile。不得用未经核验的其他 DLL 或直接原位覆盖硬链接。

## 当前宿主与最小联调

只读观察到 DSH 的 pnpm dsh web --no-open 进程与默认 ra2agent.mcp 自 16:36 起运行，早于 S4 技法改动，不能认为它们已加载最新 Python 代码。按照[指挥层的加载说明](../设计/指挥层.md#挂载方式)，联调前重启 DSH；现有服务重启会短暂中断 Web 连接与正在运行的模型回合，应单独说明并取得确认。不通过启停 bundle 热换或强杀 MCP 诱导重连，不改 preset 默认配置。

确认后先核对新 MCP 的启动时间、cwd、PYTHONPATH 及唯一控制者，再启动既有双实例名册，观察 stage、游戏帧、guard_interface_version 与己方原版身份。通过正常 status/tactics/call/cancel 入口验证卡片和单次输入，随后准备 CMIN 检查 harvest/auto_harvest 的真正接线、原生循环和重复下令情况；必要准备可请用户完成。测试采用独占指令写入者，其他连接只读；日志保存到项目忽略目录，不读取凭据或无关会话内容。

本轮不以完整模型策略评测、冷玩家唤醒、idle/dispose、持续暂停或完整联机同步为前置验收。原版输入确认与实际采矿效果分别记录；短暂切屏停帧等待恢复，未知结果不重发。测试结束关闭本轮连接和进程、恢复测试生成的配置；已明确获准的长期 DLL 启用保持，异常则按部署清单回退并更新状态。
