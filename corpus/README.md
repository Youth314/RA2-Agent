# corpus

原始语料与加工产物。**原始文件不入库**（游戏数据），来源与指纹入库。

## 原始（`raw/`，已 gitignore）

| 文件 | 来源 | 版本 | SHA-256 |
|---|---|---|---|
| `rulesmd.ini` | [yr-original-ini](https://github.com/DeathFishAtEase/yr-original-ini) 分支 `1.001` | YR 1.001 原版 | `339c826c8e925b4dfe497f67ebc9be091ab8ca0e380dc98c80e5a2449ebd02d6` |
| `artmd.ini` | 同上 | 同上 | `dcfc3d3782881c253080446e73974eb5d55366767d1e564dd2c9d4272e71056b` |
| `aimd.ini` | 同上 | 同上 | `08ed525b0b9aa47fce2090d9467c7b8cd4021777a0624fd7435acdb8c6399d11` |

- `rulesmd.ini` —— 单位、建筑、武器、装甲、造价、前提。**权威数字在这里。** 1478 节，其中有用约 665 节（`InfantryTypes` 65、`VehicleTypes` 80、`AircraftTypes` 12、`BuildingTypes` 403、`Warheads` 105、`SuperWeaponTypes` 12）；其余是树、桥、矿这些地形节。
- `artmd.ini` —— 外观（图像、动画）。对决策基本无用，留作备查。
- `aimd.ini` —— 电脑玩家的行为参数。要建模对手时用。

重取：

```sh
python3 tools/fetch_corpus.py                 # 三样都取，可重复运行（已取到的跳过）
python3 tools/fetch_corpus.py --only modenc   # 只取一样
```

## 原始（`raw/<wiki>/pages.jsonl`，已 gitignore）

一页一行：`{wiki, pageid, title, url, content}`。带 `pageid` 是为了断点续跑。

| 源 | 取法 | 页数 | 正文 |
|---|---|---|---|
| ModEnc | 主命名空间全量 | 4005 | 4.0 MB（其中 584 页是近空的地址存根与重定向） |
| C&C Fandom | 只走 `Red Alert 2*` 与 `Yuri's Revenge*` 分类，含子分类 | 480 | 2.0 MB |

Fandom 那 41,783 页里绝大多数与本项目无关（泰伯利亚、将军、RA3、剧情、图片），故按分类切。被排除的 52 个分类全是 `*images` / `*cameos` / 美术类，没有正文分类被误伤。

**字段的语义不在这三个 INI 里**，在 ModEnc 的 `Rules.ini` 一族条目：`rulesmd.ini` 给值，ModEnc 给每个键是什么意思。缺了后者，`Versus=`、`Armor=`、`Warhead=` 只是看不懂的缩写。

## 加工产物

| 路径 | 是什么 | 谁生成 |
|---|---|---|
| `derived/rules.json` | 单位/建筑/武器/弹头的结构化表，给技法层（Python）查 | `tools/build_codex.py` |
| `derived/names.json` | 注册名 → 中文名，由 B 站《红警2单位对照》抽出 | `tools/fetch_names.py` |
| `notes/` | 手写补充（科技建筑效果、俗名、中文名），生成时合并进 codex | 人 |
| `sources/` | 第三方文本快照（含出处）。知乎取不到第二份，别删 | 人 |
| [`../codex/`](../codex/) | 给模型 grep 的资料（markdown） | `tools/build_codex.py` |

```sh
python3 tools/build_codex.py
```

生成物不要手改。要改内容改 `notes/` 或改生成器。

中文名有两个来源，手写的优先：

```sh
python3 tools/fetch_names.py     # 从 B 站《红警2单位对照》抽出，写 derived/names.json
```

抽取那页要当心：建筑段写作 `ID 中文名`，单位段写作 `中文名----ID`，而单位段还会把武器跟在后面
（`GAPILL 机枪碉堡---Vulcan2`）。故抽取器拿已知的注册名去切词，并让单位与建筑优先于武器。

引擎用名字前缀 `ZZZ` 标注未使用的条目，另有 `Placeholder`、`DeathDummy` 两个占位物——这些不进正文，单列一节。
