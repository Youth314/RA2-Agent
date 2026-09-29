# codex

给模型按需 grep 的游戏资料。**生成物，不要手改。**

| 文件 | 内容 | 生成 |
|---|---|---|
| `units.md` | 每个单位一行：造价、血、装甲、速度、前提，以及主武器对每种装甲的每发伤害 | `tools/build_codex.py` |
| `buildings.md` | 可建造建筑、科技与中立建筑、可进驻建筑 | 同上 |

数字全部来自 `corpus/raw/rulesmd.ini`（原版 YR 1.001），效果文字来自 `corpus/notes/`。

**标识符保持英文**：单位名、装甲代号、前提建筑 id 都是跨语言稳定的键，翻了就与语料、游戏和回放日志断开。中文只用于解释。见 [.agents/AGENTS.md](../.agents/AGENTS.md) 的写作要求。
