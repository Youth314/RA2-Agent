# Attack 功能组集中真机操作单

日期：2026-10-03。状态：待授权，未部署/起局/下令。源码、离线检查与产物指纹只在[Attack 验证](../../notes/验证/Attack玩家接口验证.md)维护，本页规定下一整批环境改动、玩家协作与动作范围。

## 1. 批次与回滚

申请在 D:\Games\ra2probe 与 D:\Games\ra2probe-b 临时安装同一 Attack v1 DLL，保持双侧硬链接；从实际长期 Stop v1 创建持久备份和独立 deployment.json，原 Stop installed 清单不改。只使用已有配置和 MatchHost.launch 启动双窗口，不调用 render/up，不安装软件、改 spawn 配置或变更国家。开局仅确认本批 Attack/Target 版本与可用目标身份；不重跑旧加载/空 Target 对照。

批次结束关闭本轮 PID与连接，核对端口已关闭，双側 DLL 恢复实际 Stop v1 基线，硬链接和配置指纹一致，临时清单写 rolled_back。回滚不得使用硬编码 Guard 指纹的旧 Stop rollback。确实出现 unknown 时按已提交处理，先回读，不重新提交相同请求。

## 2. 对象和分工

沿用实际 Alpha 的 Alliance/AMCV 与 Beta 的 Americans。由玩家在 Beta 准备一台普通 MTNK，在 Alpha 保留一台未展开 AMCV；开始前 AMCV 在 MTNK 武器射程外、健康 1000，不允许其他单位接战。Beta 已探索 AMCV 所在格，必要时由玩家使用一个普通 Scout 揭图，确保目标对 Beta 合法可见；不能要求目标在 MTNK 视野外却又凭主持侧 Alpha 私有数据下单。玩家停止其他下令并保留 Alpha D 的操作窗口。Agent 必须经正式 attack_target 技法执行；主持侧只读，不直接调 Client 或注入单位命令，也不建立普通子 Agent 冒充玩家 agent。若本轮没有真实玩家 agent 的技法通道，先完成宿主接线，不能绕过该约束。

本批只授权该 MTNK 的两次新普通对象攻击：先点名 AMCV，后点名展开后的 GACNST。每个请求一次；cancel 仅释放租约。玩家按下面时机操作一次 D，必要准备和 MTNK 退到安全位置也属于本批明确的人工步骤。

## 3. 同一局执行顺序

| 步骤 | 动作与判据 |
|---|---|
| 前置 | 记录席位、MTNK/AMCV Agent ID、当前内部绑定与健康；确认目标在合法可见集合、命令身份字段提供、无其他写入者；人工明确 D 窗口与提示后立即按键，不在非空 Target 时等待多轮问答 |
| A1 | 真实玩家 agent 对 MTNK 调用一次 attack_target(target=AMCV ID)，只读采集新攻击输入和 actual_targets；两项均取得时记录 operation_observed，不声称已开火/击毁；采不到输入则 unknown，保留读回计划，不重发 |
| A2 | 主持侧确认当前仍是该 AMCV 的非空目标且健康 ≥700 时，立即提示玩家在 Alpha 按一次 D。若健康先低于 700 或目标已 NONE，停止该动态分支，不再用原场景声称完整非空展开通过；玩家让 MTNK 退开，主批其他步骤仍可继续 |
| A3 | 只读确认旧 AMCV pointer/native ID 已移除、新 GACNST 身份出现，核对 Target 切换/不可观测/无目标的实际记录；不得将缺席解释为击毁。若想确认旧计划不追随变身，直接在已有待回读计划上读状态，不重发旧请求 |
| A4 | 前置成立后，同一 MTNK 调用一次 attack_target(target=新 GACNST ID)，取得本次新输入和建筑 Target；必要效果如健康变化单独记录。新建筑可延续 Agent ID，但当前绑定必须重建；不沿用 AMCV 的 native ID |
| 收尾 | 统一终止本轮采集与 PID，恢复 Stop DLL；证据落到单一验证记录，未取到的动态结果保留未验，不另起局补尾窗 |

按需保留一个服务端目标 ID 不匹配用例：先由正常技法/L0 完成合法校验，再使用明确授权的实验 transport fault 在新受控请求的 expected_target_native_id 字段改成固定不匹配值，只运行一次并核对 DLL 拒绝、无该请求的新攻击输入；需要把 fault 接到真实技法通道，不由主持侧构造 Client 下单。若本批授权不含此注入，则跳过并保留原生执行复查未验，离线拒绝证据不升级为真机证明。

## 4. 批次结束条件

两次合法受控请求、动态窗口结果与必要单拒绝均分别给出限定证据；未通过或 unknown 不自动重复。游戏收尾和 Stop 恢复是本批必做部分，不等完整矩阵补齐。新 DLL 不长期启用，需另获授权。
