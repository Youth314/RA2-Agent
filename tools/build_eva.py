"""把 `evamd.ini` 里的副官语音表做成对照表。

引擎自己怎么给事件分级、怎么排队，都在这个文件里；`Text=` 还给了每个事件的原文。
**触发条件不在里面**——那是引擎代码，故「可见性」与「能否合成」两列由人写，见
`corpus/notes/eva_annotations.md`。

用法：

```sh
python3 tools/build_eva.py
```
"""
import json
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
RAW = REPO / "corpus" / "raw" / "evamd.ini"
NOTES = REPO / "corpus" / "notes" / "eva_annotations.md"
DERIVED = REPO / "corpus" / "derived"
CODEX = REPO / "codex"

#: 单位出厂报告的前缀。与 `EVA_*` 是两套机制：后者是全局警告，前者是「某单位出厂了」。
UNIT_PREFIXES = ("Unit_Eva_", "Unit_Sofia_")
#: `Priority=` 的档位，由重到轻。引擎拿它决定播报的取舍。
PRIORITY_ORDER = ("CRITICAL", "IMPORTANT", "NORMAL", "LOW")
#: 单位出厂报告的默认标注。引擎无条件全图播报「某单位出厂了」，而我们的观测按
#: 迷雾过滤、也不读敌方内部状态，故这类事件合成不了。个别可覆盖。
UNIT_REPORT_DEFAULT = {
    "visibility": "全图", "synthesizable": "不可",
    "basis": "引擎全图播报；观测按迷雾过滤",
}

#: 标注行的第一条必须是这个名字形状；说明文字据此跳过。
IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
#: 注释里用 `|` 分隔；第一条是事件名。
ANNOTATION_FIELDS = ("visibility", "synthesizable", "basis")


def parse_ini(text):
    """节名 → 键值。`;` 之后是注释。"""
    out = {}
    # 注释用 `[^\n]*` 而非 `.*`：`re.S` 下 `.` 会吃换行，把后面整个文件吞掉
    for match in re.finditer(r"^\[([^\]]+)\][ \t]*(?:;[^\n]*)?$\n(.*?)(?=^\[|\Z)",
                             text, re.M | re.S):
        data = {}
        for line in match.group(2).splitlines():
            line = line.split(";")[0].strip()
            if "=" in line:
                key, _, value = line.partition("=")
                data[key.strip()] = value.strip()
        out[match.group(1)] = data
    return out


def load_annotations():
    """手写的可见性与合成性；一行 `事件名 | 可见性 | 可合成 | 依据`。"""
    out = {}
    if not NOTES.exists():
        return out
    for raw in NOTES.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        parts = [piece.strip() for piece in line.split("|")]
        name = parts[0]
        if not IDENTIFIER.match(name):
            continue
        out[name] = dict(zip(ANNOTATION_FIELDS, parts[1:] + [""] * len(ANNOTATION_FIELDS)))
    return out


def collect(sections, annotations):
    """EVA 事件与单位出厂报告，各带引擎原文、优先级、排队语义与人工标注。"""
    events, reports = [], []
    for name, data in sections.items():
        entry = {
            "name": name,
            "text": data.get("Text", "").strip(),
            "priority": data.get("Priority", "").strip().upper(),
            "queue": "QUEUE" in data.get("Type", "").upper(),
        }
        entry.update({k: "" for k in ANNOTATION_FIELDS})
        entry.update({k: v for k, v in annotations.get(name, {}).items() if v})
        if name.startswith(UNIT_PREFIXES):
            entry.update(UNIT_REPORT_DEFAULT)
            entry.update({k: v for k, v in annotations.get(name, {}).items() if v})
            prefix = next(p for p in UNIT_PREFIXES if name.startswith(p))
            entry["unit"] = name[len(prefix):]
            entry["voice"] = "sofia" if prefix == "Unit_Sofia_" else "eva"
            reports.append(entry)
        elif name.upper().startswith("EVA_"):
            events.append(entry)
    events.sort(key=lambda e: (PRIORITY_ORDER.index(e["priority"])
                               if e["priority"] in PRIORITY_ORDER else len(PRIORITY_ORDER),
                               e["name"]))
    reports.sort(key=lambda e: (e["unit"], e["voice"]))
    return events, reports


def render(events, reports, annotations):
    """`codex/eva.md`：给人核对的对照表。"""
    known = sum(1 for e in events if e["visibility"])
    lines = [
        "# 副官事件",
        "",
        "由 `corpus/raw/evamd.ini` 生成，不要手改。**可见性与合成性两列来自人写的 "
        "`corpus/notes/eva_annotations.md`**，其余都是引擎原文。",
        "",
        f"共 {len(events)} 个 `EVA_*` 事件、{len(reports)} 条 `Unit_*_<Type>` 单位出厂报告。",
        "",
        "两套机制：`EVA_*` 是全局警告；`Unit_*_<Type>` 是「某单位出厂了」，单位与建筑都有，"
        "Eva 与 Sofia 两套副官各一份。这类报告引擎无条件全图播报，"
        "**我们拿不到**——观测按迷雾过滤。",
        "",
        "`优先级` 与 `排队` 是引擎自己的取值——拿它决定哪些事件值得叫醒模型，"
        "不必另立一套。",
        "",
        "## 事件",
        "",
        "| 事件 | 引擎原文 | 优先级 | 排队 | 可见性 | 可合成 | 依据 |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in events:
        lines.append("| `{}` | {} | {} | {} | {} | {} | {} |".format(
            e["name"], e["text"] or "—", e["priority"] or "—",
            "是" if e["queue"] else "", e["visibility"] or "**待核**",
            e["synthesizable"] or "**待核**", e["basis"] or ""))
    lines += ["", f"## 单位出厂报告（{len(reports)}）", "",
              "含建筑。名字里的 `<Type>` 与 `rulesmd.ini` 的类型节对应，"
              "但拼写有出入（`YuriEng`、`BatLabYuri`），需要时对照 `codex/units.md`。",
              "",
              "| 名称 | 单位 | 副官 | 引擎原文 | 优先级 | 可见性 | 可合成 |",
              "|---|---|---|---|---|---|---|"]
    for r in reports:
        lines.append("| `{}` | {} | {} | {} | {} | {} | {} |".format(
            r["name"], r["unit"], "Zofia" if r["voice"] == "sofia" else "Eva",
            r["text"] or "—", r["priority"] or "—", r["visibility"] or "**待核**",
            r["synthesizable"] or "**待核**"))
    unused = sorted(set(annotations) - {e["name"] for e in events + reports})
    if unused:
        lines += ["", "## 标注里认不出的名字", "",
                  "`corpus/notes/eva_annotations.md` 里这些名字在 `evamd.ini` 中不存在：", ""]
        lines += [f"- `{name}`" for name in unused]
    lines.append("")
    return "\n".join(lines)


def main():
    if not RAW.exists():
        print(f"缺 {RAW}；见 corpus/README.md 的来源与校验和", file=sys.stderr)
        return 1
    # 原版 INI 是 CP1252：`\x85` 是省略号，`\x92` 是右单引号
    sections = parse_ini(RAW.read_bytes().decode("cp1252", errors="replace"))
    annotations = load_annotations()
    events, reports = collect(sections, annotations)

    unknown = sorted(set(annotations) - {e["name"] for e in events + reports})
    if unknown:
        for name in unknown:
            print(f"标注里认不出的名字：{name}", file=sys.stderr)
        return 1

    with_queue = sum(1 for e in events if e["queue"])
    print(f"EVA_* 事件 {len(events)}（排队播报 {with_queue}）、"
          f"单位出厂报告 {len(reports)}")
    DERIVED.mkdir(parents=True, exist_ok=True)
    (DERIVED / "eva.json").write_text(json.dumps(
        {"source": "corpus/raw/evamd.ini", "events": events, "unit_reports": reports},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (CODEX / "eva.md").write_text(render(events, reports, annotations), encoding="utf-8")
    print("→ corpus/derived/eva.json  codex/eva.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
