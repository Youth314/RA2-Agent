# ra2-agent

一个能玩《红色警戒2》/《尤里的复仇》的 Agent 系统。

- 支持玩家、Agent、游戏内置电脑玩家之间的自由组合对战
- 允许玩家在 Agent 决策的各层级介入

## 状态

早期阶段。引擎可行性与命令能力均已实测验证，见 [.agents/notes/命令能力测绘结果.md](.agents/notes/命令能力测绘结果.md)。基础设施层（协议、状态、校验、意图、对象标识、观测、执行器）、技法层（技法框架、运行时、6 条示范技法）与指挥层工具面（局内四工具加门外的 `game`）已实现，全部可离线测试；DSH 侧以 agent preset `ra2` 挂载，装在 `dsh/`。设计见 [.agents/notes/技法框架.md](.agents/notes/技法框架.md) 与 [.agents/notes/指挥层.md](.agents/notes/指挥层.md)。

## 目录

- `proto/` — ra2yrcpp 的 protobuf 接口定义，上游快照
- `src/ra2agent/` — Agent 与引擎适配层的源码
- `tests/` — 单元测试
- `tools/` — 探针与运维脚本
- `corpus/` — 原始语料与来源记录，见 [corpus/README.md](corpus/README.md)
- `dsh/` — DSH 侧的挂载物：声明 agent preset `ra2` 的 bundle
- `docs/` — 给人看的文档
- `.agents/` — 给 agent 看的内容，见 [.agents/AGENTS.md](.agents/AGENTS.md)

## 开发

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

要开游戏跑真机测试，见 [.agents/notes/真机测试手册.md](.agents/notes/真机测试手册.md)（启动、焦点、跑批、留证与坑清单）。

要让同一台机器上的两个实例对战，见 [.agents/notes/双实例联机.md](.agents/notes/双实例联机.md)（单实例守卫与失焦暂停两道墙、`spawn.ini` 席位语义、验收判据）。

引擎侧接口的实测结论见 [.agents/notes/命令能力测绘结果.md](.agents/notes/命令能力测绘结果.md)。
