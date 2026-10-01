# dsh

DSH 侧的挂载物：一个 bundle，声明 agent preset `ra2`。

| 文件 | 是什么 |
|---|---|
| `package.json` | bundle 清单 |
| `cordis.patch.yml` | preset `ra2` 的完整声明，生成物，别手改 |
| `generate.py` | 从 DSH 的 `cordis` preset 生成上一条，`--check` 比对是否同步 |

装法与取舍见 [指挥层](../.agents/notes/设计/指挥层.md#挂载方式)。
