# ra2-agent

一个能玩《红色警戒2》/《尤里的复仇》的 Agent 系统。

- 支持玩家、Agent、游戏内置电脑玩家之间的自由组合对战
- 允许玩家在 Agent 决策的各层级介入

## 状态

早期阶段。引擎可行性与命令能力均已实测验证，见 [.agents/notes/命令能力测绘结果.md](.agents/notes/命令能力测绘结果.md)。L0 适配层已实现协议、状态、校验、意图、对象标识、观测与执行器；L1 及以上的决策层未开始。

## 目录

- `proto/` — ra2yrcpp 的 protobuf 接口定义，上游快照
- `src/ra2agent/` — Agent 与引擎适配层的源码
- `tests/` — 单元测试
- `tools/` — 探针与运维脚本
- `docs/` — 给人看的文档
- `.agents/` — 给 agent 看的内容，见 [.agents/AGENTS.md](.agents/AGENTS.md)

## 开发

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

引擎侧接口的实测结论见 [.agents/notes/命令能力测绘结果.md](.agents/notes/命令能力测绘结果.md)。
