# 基线 DLL 加载验证

日期：2026-10-02。范围：S3 本地构建基底的临时 DLL 替换、双实例加载与只读接口兼容性。用户已单独确认替换、启动和恢复。结果为限定通过；不包含新操作、单位下令、联机同步验收、真实 DSH 生命周期或持续暂停恢复验证。构建版本、产物哈希和复跑入口在[DLL 构建准备](../环境/DLL构建准备.md)维护。

## 执行与证据

预检查未发现 gamemd 进程，探针端口未监听。原两侧 libra2yrcpp.dll 为同一 inode 的两个硬链接；先将 DLL、spawn.ini 与已有 spawn.ini.render-bak 复制到独立备份，再通过临时文件替换 DLL，未直接覆写共享文件。按 config/match.json 现有名册渲染 spawn.ini 并启动两侧；未改动名册、显示设置、ra2yrcpp.json 或 DSH 配置。

脚本为 .agents/tmp/engine-build/load_check.py，记录、备份、前后游戏日志和崩溃报告在 .agents/tmp/engine-build/backups/20261002-151229/；主记录为 validation.json。临时脚本自行关闭短连接与采集连接，成功或失败均进入停止和恢复流程；本轮进程 PID 为 Alpha=30352、Beta=4752，仅按本轮路径归属的 PID 停止。

读操作包括 GetSystemState 握手、GetGameState、InspectConfiguration 的只读调用、ReadValue 的地图与初始类型表；不创建 GameSession，不启动模型 / 自动技法，不发单位命令。采样间隔约一秒，共十二组顺序读取；读取和解析耗时使间隔不保证恰好一秒，Alpha/Beta 的读取也不是同一时刻快照。

| 项目 | Alpha | Beta |
|---|---|---|
| 进局 stage | 2 | 2 |
| 唯一 current_player | Alpha，house_index=1 | Beta，house_index=0 |
| 实际 faction | Alliance | Americans |
| 己方对象 | 11；均可关联已读类型表 | 11；均可关联已读类型表 |
| 类型表 / 地图 | 3875 条，144×144 | 3875 条，144×144 |
| single_step | False | False |
| 首末采样 frame | 70 → 743 | 84 → 765 |
| frame 推进 | 单调推进，增加 673 | 单调推进，增加 681 |
| 原版事件解析 | 十二组状态均可解析，保留公共当前玩家视图与内部完整列表 | 十二组状态均可解析，保留公共当前玩家视图与内部完整列表 |

## 限制与日志

两侧顺序采样帧差为 14–22 帧，不满足按一帧上下判断同步的完整联机验收要求。此次只确认两个进程进入对局且各自帧推进，未核验 UDP 双向包、CRC 一致性或确定帧差来源；不能宣称已完成新 DLL 的联机一致性验证。同步检查需要更准确地关联读取时刻与网络帧，按后续命令问题选择补测，不通过放宽阈值标为已通过。

日志出现 unknown TypeClass，包括 18（YRpp 的 IsotileType）；替换前保存的原 DLL 日志中已有同类警告，固定源码 TypeClassParser 也只处理有限类型。这不构成完整类型读取成功结论，本轮只检查己方对象的 type_pointer 可关联 TypeTable。EXCEPT_CNCNET.TXT 与 except.txt 的前后内容均一致，没有新增崩溃报告；短时运行不证明长期稳定性。

原版事件没有人工操作输入，不能证明新的 Guard / Escort / Harvest 命令等价。S2 玩家操作证据继续由[能力表](../引擎/玩家操作能力表.md#s2-现场记录)维护；只读解析回归见[原版事件接口验证](原版事件接口验证.md)。持续暂停恢复未验，HARV 按用户决定不重测，模型只调用技法。

## 停止与恢复

本轮两实例已停止，14521 / 14522 端口均关闭，采集连接与脚本已退出。两侧 DLL、spawn.ini 和既有 spawn.ini.render-bak 已按本轮独立备份恢复，并逐项核对 SHA-256；两侧 DLL 原先的硬链接关系也已重建。原 DLL 恢复哈希为 59b8d235a44398f20d290b44b60b92d7127fada1353cfe1d2bfd0a8b646a0b28。游戏自动产生的日志保留，前后副本已留证；未删除历史证据。

系统 libwinpthread.a 的 SHA-256 仍为 85a42ca8b10dc8602de9dc95cdaf86a95d8687763431f041be3762be4bc6dfc7，与构建清单一致，项目内移除版本资源没有修改系统库。新的 DLL 仅保存在构建产物目录，当前游戏仍使用原 DLL。

## 后续

构建与限定加载基底已建立。下一项为受控 GuardCurrent / GuardPosition 的类型化请求、DLL 能力声明、安全翻译与最少对象级回读；旧 DLL 明确 unsupported。先固化构建补丁与 Python 接口，再进行相关离线和真机对照。新功能 DLL 替换与后续测试场景须重新说明具体内容，本次临时基线验证授权不等于永久部署或任意测试授权。
