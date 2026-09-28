# ra2-agent

一个能玩《红色警戒2》/《尤里的复仇》的 Agent 系统。

- 支持玩家、Agent、游戏内置电脑玩家之间的自由组合对战
- 允许玩家在 Agent 决策的各层级介入

## 状态

早期阶段。引擎侧的可行性已验证，见 [.agents/notes/探针实验结论.md](.agents/notes/探针实验结论.md)。

## 目录

- `proto/` — ra2yrcpp 的 protobuf 接口定义，上游快照
- `src/` — Agent 与引擎适配层的源码（尚未开始）
- `tools/` — 探针与运维脚本
- `docs/` — 给人看的文档
- `.agents/` — 给 agent 看的内容，见 [.agents/AGENTS.md](.agents/AGENTS.md)
