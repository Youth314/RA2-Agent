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

暂无。加工结果放哪见 [.agents/notes/](../../.agents/notes/) 的讨论。
