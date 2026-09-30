#!/usr/bin/env python3
"""由 `corpus/raw/rulesmd.ini` 生成 `codex/` 与 `corpus/derived/rules.json`。

产物入库：写技法与回放都在离线跑，干净 checkout 要能直接用；版本变了 git diff 也
看得见。原始文件不入库，见 `corpus/README.md`。

手写补充放 `corpus/notes/`，本脚本会合并进去；生成物不要手改。

    python3 tools/build_codex.py
"""
import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from ra2agent.rules import ARMOR_TYPES, parse_rules  # noqa: E402

RAW = REPO / "corpus" / "raw" / "rulesmd.ini"
DERIVED = REPO / "corpus" / "derived" / "rules.json"
CODEX = REPO / "codex"
NOTES = REPO / "corpus" / "notes"

#: 单位与建筑的名字来源是英文，这里只把「类别」说成中文。
KIND_LABEL = {"infantry": "步兵", "vehicle": "载具", "aircraft": "飞行器"}
#: 窃取科技的三方说法（`RequiresStolen*Tech`），与 `catalogue.STOLEN_TECH` 一致。
STOLEN_LABEL = {"allied": "盟军", "soviet": "苏军", "third": "尤里"}

#: `GDI`/`Nod` 是西木从泰伯利亚之日留下的名字，实际就是盟军与苏军。
#: 阵营归属不写死在这里——`rulesmd.ini` 各国家节的 `Side=` 就是答案。
SIDE_LABEL = {"GDI": "盟军（GDI）", "Nod": "苏军（Nod）", "ThirdSide": "尤里（ThirdSide）"}
#: 单位归不到单一阵营时放这里。
SHARED_LABEL = "跨阵营"
#: 建造厂 → 阵营。建筑的阵营靠前提链追到它。
CONSTRUCTION_YARDS = {"GACNST": "GDI", "NACNST": "Nod", "YACNST": "ThirdSide"}
def country_side(rules, country):
    """某个国家属于哪个阵营。"""
    found = rules.countries.get(country)
    return found.side if found else None


def unit_side(unit, sides_of):
    """单位属于哪个阵营；横跨多个阵营返回 `None`。"""
    sides = {sides_of.get(c) for c in unit.owners} - {None}
    return sides.pop() if len(sides) == 1 else None


def building_side(building, index, seen=None):
    """建筑的阵营：顺着 `Prerequisite` 追到建造厂。

    `Owner` 对建筑不起作用——53 个可建造建筑的 `Owner` 全都列了所有国家。
    真正限定阵营的是前提链：你只有一种建造厂，链上不通就造不了。通用前提
    （`RADAR`、`PROC` 之类）本身不含建造厂，跳过即可。
    """
    if building.id in CONSTRUCTION_YARDS:
        return CONSTRUCTION_YARDS[building.id]
    seen = seen if seen is not None else set()
    if building.id in seen:
        return None
    seen.add(building.id)
    for identifier in building.prerequisite:
        parent = index.get(identifier)
        if parent is not None:
            side = building_side(parent, index, seen)
            if side:
                return side
    return None


def damage_profile(rules, holder):
    """算一个单位/建筑的主武器对每种装甲的每发伤害。

    返回 `(武器, [11 个伤害])`；没有武器或链条断了返回 `(None, ())`。
    """
    weapon = rules.weapons.get(holder.primary)
    if weapon is None:
        return None, ()
    warhead = rules.warheads.get(weapon.warhead)
    if warhead is None:
        return None, ()
    return weapon, [weapon.damage * warhead.multiplier(armor) for armor in ARMOR_TYPES]


def format_damage(values):
    """把 11 个伤害压成一行：同值的装甲并成一档。

    用 `=` 分隔是必须的——`special_1` 结尾是数字，`special_115` 分不清是
    `special_1` 打 15 还是别的。
    """
    groups = {}
    for armor, value in zip(ARMOR_TYPES, values):
        groups.setdefault(value, []).append(armor)
    return " ".join(f"{','.join(armors)}={value:g}" for value, armors in groups.items())


def unit_line(rules, unit, names, effects=None):
    """一个单位一行。"""
    effects = effects or {}
    fields = [f"**{unit.id}** {with_name(unit, names)}",
              KIND_LABEL.get(unit.kind, unit.kind),
              f"造价 {unit.cost}", f"血 {unit.strength}", unit.armor,
              f"速 {unit.speed}", f"视野 {unit.sight}"]
    if unit.prerequisite:
        fields.append("前提 " + ",".join(unit.prerequisite))
    fields.append(f"等级 {unit.tech_level}")
    if getattr(unit, "stolen_tech", ""):
        fields.append(f"需窃取{STOLEN_LABEL.get(unit.stolen_tech, '')}科技")
    if unit.passengers:
        fields.append(f"载员 {unit.passengers}")
    if house_note(unit):
        fields.append(house_note(unit))
    weapon, values = damage_profile(rules, unit)
    if weapon is not None:
        fields.append(f"{weapon.id}({weapon.damage}伤/{weapon.rof}帧/射程{weapon.rng:g} 弹头{weapon.warhead})")
        fields.append("每发 → " + format_damage(values))
    return with_effect(" · ".join(fields), effects, unit)


def building_line(rules, building, names, effects=None):
    """一个可建造建筑一行。"""
    effects = effects or {}
    fields = [f"**{building.id}** {with_name(building, names)}", f"造价 {building.cost}",
              f"血 {building.strength}", building.armor]
    if building.power:
        fields.append(f"电力 {building.power:+d}")
    if building.prerequisite:
        fields.append("前提 " + ",".join(building.prerequisite))
    fields.append(f"等级 {building.tech_level}")
    if getattr(building, "water_bound", False):
        fields.append("临水（基地附近要有水面）")
    if building.special:
        fields.append(" ".join(building.special))
    if house_note(building):
        fields.append(house_note(building))
    weapon, values = damage_profile(rules, building)
    if weapon is not None:
        fields.append(f"{weapon.id}({weapon.damage}伤/{weapon.rof}帧/射程{weapon.rng:g} 弹头{weapon.warhead})")
        fields.append("每发 → " + format_damage(values))
    return with_effect(" · ".join(fields), effects, building)


#: `ID 中文名：俗名…`；`❓` 表示中文名是按英文名推的，没经人确认。
_GLOSSARY_ENTITY = re.compile(r"^([A-Z][A-Z0-9_]{1,15})\s+(\S[^：:]*?)\s*[：:](.*)$")
_GLOSSARY_TERM = re.compile(r"^([^：:]+)[：:](.*)$")


def load_glossary():
    """读 `corpus/notes/glossary.md`。

    返回 `(实体, 战术黑话)`。实体是 `{id, name, nicknames, unconfirmed}`。
    """
    path = NOTES / "glossary.md"
    if not path.exists():
        return [], []
    entities, terms, section = [], [], ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            section = line[3:].strip()
            continue
        if not line or line.startswith("#"):
            continue
        unconfirmed = "❓" in line
        line = line.replace("❓", "").strip()
        match = _GLOSSARY_ENTITY.match(line)
        if match and section and section != "战术黑话":
            nicknames = [n.strip() for n in re.split(r"[、,]", match.group(3))
                         if n.strip() and n.strip() != "无"]
            entities.append({"id": match.group(1), "name": match.group(2),
                             "nicknames": nicknames, "unconfirmed": unconfirmed})
            continue
        if section != "战术黑话":
            continue
        match = _GLOSSARY_TERM.match(line)
        if match:
            terms.append({"term": match.group(1).strip(), "meaning": match.group(2).strip()})
    return entities, terms


def build_glossary(entities, terms):
    """`codex/glossary.md`：社区叫法，给人认人话用，不作键。"""
    lines = ["# 俗名对照", "",
             "**社区叫法，不是权威命名**，同一个东西各地叫法不同。只作**识别人话**用，"
             "**不作键**——键仍然是 `rulesmd.ini` 的注册名。",
             "", "一行一条：`注册名 中文标准名：俗名…`。带 ❓ 的中文名是按英文名推的，未经确认。", ""]
    for entity in entities:
        mark = " ❓" if entity["unconfirmed"] else ""
        nick = "、".join(entity["nicknames"]) or "（无）"
        lines.append(f"- **{entity['id']}** {entity['name']}{mark}：{nick}")
    if terms:
        lines += ["", "## 战术黑话", "",
                  "玩家会直接拿这些下指令，模型听不懂就没法介入。", ""]
        lines += [f"- **{t['term']}**：{t['meaning']}" for t in terms]
    return "\n".join(lines).rstrip() + "\n"


#: 引擎标注未使用的方式：名字前缀 `ZZZ`，或整名就是占位物。
UNUSED_PREFIX = "ZZZ"
UNUSED_NAMES = frozenset({"Placeholder", "DeathDummy"})


def load_names():
    """中文名：`corpus/derived/names.json`（抽取）+ `corpus/notes/names.md`（手写，优先）。"""
    names = {}
    derived = REPO / "corpus" / "derived" / "names.json"
    if derived.exists():
        names.update(json.loads(derived.read_text(encoding="utf-8"))["names"])
    path = NOTES / "names.md"
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            identifier, _, name = line.partition(" ")
            if name.strip():
                names[identifier.strip()] = name.replace("❓", "").strip()
    return names


def is_scrapped(holder):
    """废案：标了国家特有，但科技等级为负。

    单看 `TechLevel=-1` 不能判废案——建造厂、围墙、平民也是 -1。同时要求
    `RequiredHouses` 非空，正好只命中韩国的榴弹炮与古巴的雌鹿。
    """
    return is_country_unique(holder) and holder.tech_level < 1


def is_campaign(holder):
    """战役特供：科技等级超过 10（正常玩法最高 10）。"""
    return not is_unused(holder) and holder.tech_level > 10


def with_effect(line, effects, holder):
    """条目末尾缀上补充说明；没有就不缀。"""
    text = effects.get(holder.id)
    return f"{line} · 注：{text}" if text else line


def is_country_unique(holder):
    """只有某个国家能造：`RequiredHouses` 非空。"""
    return bool(getattr(holder, "required_houses", ()))


def country_uniques(rules):
    """按国家收拢国家特有的单位与建筑。

    阵营只管共用部分——法国与英国同属盟军，但法国多一门巨炮；伊拉克与俄罗斯
    同属苏军，但伊拉克多辐射兵。故国家的特有项单独成册，不混进阵营章。
    """
    out = {}
    for holder in list(rules.units) + list(rules.buildings):
        if is_unused(holder) or is_scrapped(holder) or not is_country_unique(holder):
            continue
        for country in holder.required_houses:
            out.setdefault(country, []).append(holder)
    return out


def sides_of(rules):
    """国家 id → 阵营。"""
    return {c.id: c.side for c in rules.countries.values()}


def side_members(rules, side, buildings=False):
    """某个阵营的共用条目；国家特有的不在其中。"""
    index = {b.id: b for b in rules.buildings}
    country_sides = sides_of(rules)
    pick = (lambda o: True) if buildings else (lambda o: o.tech_level >= 1)
    if buildings:
        pick = lambda o: o.cost > 0 and o.tech_level >= 1        # noqa: E731
    out = []
    for holder in rules.buildings if buildings else rules.units:
        if (is_unused(holder) or is_country_unique(holder)
                or is_campaign(holder) or not pick(holder)):
            continue
        side_of = building_side(holder, index) if buildings else unit_side(holder, country_sides)
        if side_of == side:
            out.append(holder)
    return out


def is_unused(holder):
    """引擎标注未使用的条目。"""
    return holder.name.startswith(UNUSED_PREFIX) or holder.name in UNUSED_NAMES


def house_note(holder):
    """阵营限制说成人话；没有限制就不占位。"""
    parts = []
    if getattr(holder, "required_houses", ()):
        parts.append("仅 " + ",".join(holder.required_houses))
    if getattr(holder, "forbidden_houses", ()):
        parts.append("禁 " + ",".join(holder.forbidden_houses))
    return " · ".join(parts)


def with_name(holder, names):
    """把中文名缀在英文名后面；没有就不缀。"""
    chinese = names.get(holder.id)
    return f"{holder.name}（{chinese}）" if chinese else holder.name


def load_notes(name):
    """读 `corpus/notes/<name>` 的手写补充：一行一条，`ID 正文`。"""
    path = NOTES / name
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        identifier, _, text = line.partition(" ")
        out[identifier.strip()] = text.strip()
    return out


def build_units(rules, names, effects=None):
    """`codex/units.md`：按阵营分，未使用的排最后。"""
    country_sides = sides_of(rules)
    buildable = [u for u in rules.units if u.tech_level >= 1 and not is_unused(u)]
    # 国家特有的也在这条线上，但它们归属 countries.md，别在这里重复出现
    other = [u for u in rules.units
             if u.tech_level < 1 and not is_unused(u)
             and not is_country_unique(u) and not is_campaign(u)]
    unused = [u for u in rules.units if is_unused(u)]
    groups = []
    for side in ("GDI", "Nod", "ThirdSide"):
        part = side_members(rules, side)
        if part:
            groups.append((SIDE_LABEL[side], part))
    shared = [u for u in buildable
              if unit_side(u, country_sides) is None and not is_country_unique(u)]
    if shared:
        groups.append((SHARED_LABEL, shared))
    lines = ["# 单位",
             "",
             f"由 `corpus/raw/rulesmd.ini` 生成，共 {len(rules.units)} 个："
             f"可建造 {len(buildable)}：盟军共用 {len(side_members(rules, 'GDI'))}、"
             f"苏军共用 {len(side_members(rules, 'Nod'))}、"
             f"尤里共用 {len(side_members(rules, 'ThirdSide'))}、"
             f"跨阵营 {len(shared)}、国家特有 {len([u for u in buildable if is_country_unique(u)])}；"
             f"其它（民用、任务用）{len(other)}，未使用 {len(unused)}。不要手改。",
             "",
             "**先看自己是哪个国家**：阵营章只有该阵营的共用单位，各国特有的在 "
             "[`countries.md`](countries.md)。",
             "",
             "「每发 →」是主武器对每种装甲的每次开火伤害，同值的并成一档；"
             "装甲代号顺序同 `corpus/derived/rules.json` 的 `armor_types`。",
             ""]
    for title, group in groups:
        lines += [f"## {title}（{len(group)}）", ""]
        lines += [f"- {unit_line(rules, unit, names, effects)}" for unit in group]
        lines.append("")
    if other:
        lines += [f"## 民用与其它（{len(other)}）", ""]
        lines += [f"- {unit_line(rules, unit, names, effects)}" for unit in other]
        lines.append("")
    campaign = [u for u in rules.units if is_campaign(u)]
    if campaign:
        lines += [f"## 战役特供（{len(campaign)}）", "",
                  "科技等级超过 10，正常对战里造不出来。", ""]
        lines += [f"- {unit_line(rules, unit, names, effects)}" for unit in campaign]
        lines.append("")
    if unused:
        lines += [f"## 未使用（{len(unused)}）", "",
                  "引擎用名字前缀 `ZZZ` 标注，留着只为了表里没有悬空引用。", ""]
        lines += [f"- **{u.id}** {u.name}" for u in unused]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_buildings(rules, names, effects=None):
    """`codex/buildings.md`。"""
    notes = load_notes("tech_buildings.md")
    buildable = [b for b in rules.buildings if b.cost > 0 and b.tech_level != -1]
    # 科技建筑没有专门的旗标，靠游戏自己的命名约定认：名字以 `Tech ` 开头。
    # 另有几个也能占领但只是地图装饰（民用医院、复活节岛石像），归到「其它可占领」。
    tech = [b for b in rules.buildings if b.capturable and b.name.startswith("Tech ")]
    neutral = [b for b in rules.buildings
               if b.capturable and b.cost == 0 and not b.can_be_occupied
               and not b.name.startswith("Tech ")]
    occupied = [b for b in rules.buildings if b.max_occupants > 0]

    lines = ["# 建筑", "",
             f"由 `corpus/raw/rulesmd.ini` 生成，共 {len(rules.buildings)} 个，不要手改。"
             f"其中可建造 {len(buildable)}、科技与中立 {len(tech)}、可进驻 {len(occupied)}。"
             "带 `仅 X` 的是**国家特有**。",
             "", "## 科技与中立", "",
             "占了有用的那些。效果由人写（`corpus/notes/tech_buildings.md`）。", ""]
    for building in tech:
        effect = notes.get(building.id, "（待写）")
        lines.append(f"- **{building.id}** {building.name} — {effect}")
    if neutral:
        lines += ["", "也能占领，但只是地图装饰：",
                  " ".join(f"{b.id}({b.name})" for b in neutral)]
    lines += ["", "## 可建造", "",
              "阵营由前提链追到建造厂决定——建筑的 `Owner` 全都列了所有国家，"
              "分不出来；真正限定阵营的是「你只有一种建造厂」。",
              "各国特有的在 [`countries.md`](countries.md)。", ""]
    for side in ("GDI", "Nod", "ThirdSide", None):
        group = side_members(rules, side, buildings=True) if side else [
            b for b in buildable if building_side(b, {x.id: x for x in rules.buildings}) is None]
        if not group:
            continue
        title = SIDE_LABEL[side] if side else "未归类"
        lines += [f"### {title}（{len(group)}）", ""]
        lines += [f"- {building_line(rules, building, names, effects)}" for building in group]
        lines.append("")
    lines += ["", "## 可进驻", "",
              "拿来当掩体的。只给大小与驻军上限。", "",
              "| 建筑 | 名字 | 地基 | 驻军上限 | 装甲 | 血 |", "|---|---|---|---|---|---|"]
    for building in sorted(occupied, key=lambda b: (-b.max_occupants, b.id)):
        lines.append(f"| {building.id} | {with_name(building, names)} | {building.foundation or '—'} | "
                     f"{building.max_occupants} | {building.armor} | {building.strength} |")
    return "\n".join(lines).rstrip() + "\n"


def build_countries(rules, names, effects=None):
    """`codex/countries.md`：先定位自己是哪个国家，再看能造什么。"""
    uniques = country_uniques(rules)
    lines = ["# 国家", "",
             "一局的参战方是**国家**，不是阵营。每个国家能造的东西 = "
             "**本阵营的共用清单** + **自己的特有项**。",
             "",
             "阵营共用在 [`units.md`](units.md) 与 [`buildings.md`](buildings.md) 的对应章；"
             "各国特有的都在这里。", ""]
    playable = sorted((c for c in rules.countries.values() if c.playable),
                      key=lambda c: (c.side, c.id))
    for country in playable:
        label = names.get(country.id, "")
        # 观测里给的是显示名（`America`），这里带上，模型才对得上
        title = f"{country.id} {country.display}"
        if label and label != country.display:
            title += f"（{label}）"
        lines += [f"## {title} — {SIDE_LABEL.get(country.side, country.side)}", ""]
        group = uniques.get(country.id, [])
        lines += ["特有：（无）", ""] if not group else ["特有：", ""]
        for holder in group:
            line = (unit_line(rules, holder, names, effects) if hasattr(holder, "kind")
                    else building_line(rules, holder, names, effects))
            lines.append(f"- {line}")
        scrapped = [o for o in list(rules.units) + list(rules.buildings)
                    if is_scrapped(o) and country.id in o.required_houses]
        if scrapped:
            lines += ["", "废案（游戏里造不出来，科技等级为负）：", ""]
            for holder in scrapped:
                line = (unit_line(rules, holder, names, effects) if hasattr(holder, "kind")
                        else building_line(rules, holder, names, effects))
                lines.append(f"- {line}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def dump_json(rules):
    """`corpus/derived/rules.json`：给技法层（Python）查的结构化数据。"""
    return json.dumps({
        "armor_types": list(ARMOR_TYPES),
        "units": [asdict(u) for u in rules.units],
        "buildings": [asdict(b) for b in rules.buildings],
        "weapons": {k: asdict(v) for k, v in sorted(rules.weapons.items())},
        "warheads": {k: asdict(v) for k, v in sorted(rules.warheads.items())},
    }, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


_EMITTED = re.compile(r"^- \*\*([A-Za-z][A-Za-z0-9_]{1,15})\*\*|^\| ([A-Za-z][A-Za-z0-9_]{1,15}) \|",
                     re.M)


def emitted(text):
    """文档里列出的注册名。"""
    return [a or b for a, b in _EMITTED.findall(text)]


def check_coverage(rules):
    """每个单位都要出现；国家特有的只能出现在 `countries.md`。

    装饰性建筑（既不可造也不可进驻）本就不列，故只查单位与「该出现的建筑」。
    """
    units_text = (CODEX / "units.md").read_text(encoding="utf-8")
    builds_text = (CODEX / "buildings.md").read_text(encoding="utf-8")
    country_text = (CODEX / "countries.md").read_text(encoding="utf-8")
    problems = []

    listed = emitted(units_text) + emitted(country_text)
    known = {u.id for u in rules.units}
    for identifier in sorted(known - set(listed)):
        problems.append(f"单位 {identifier} 没有出现在任何文档里")

    uniques = {o.id for o in list(rules.units) + list(rules.buildings)
               if is_country_unique(o) and not is_unused(o)}
    leaked = sorted(uniques & set(emitted(units_text) + emitted(builds_text)))
    if leaked:
        problems.append(f"国家特有的条目混进了阵营章：{leaked}")
    for identifier in sorted(uniques - set(emitted(country_text))):
        problems.append(f"国家特有的 {identifier} 没有出现在 countries.md 里")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成 codex 与派生数据")
    parser.add_argument("--rules", default=str(RAW))
    args = parser.parse_args(argv)
    source = Path(args.rules)
    if not source.exists():
        print(f"缺少 {source}。先跑 python3 tools/fetch_corpus.py", file=sys.stderr)
        return 1
    rules = parse_rules(source.read_text(encoding="utf-8", errors="replace"))

    DERIVED.parent.mkdir(parents=True, exist_ok=True)
    CODEX.mkdir(parents=True, exist_ok=True)
    names = load_names()
    effects = load_notes("entry_notes.md")
    entities, terms = load_glossary()
    known = ({u.id for u in rules.units} | {b.id for b in rules.buildings}
             | set(rules.weapons))
    unknown = sorted({e["id"] for e in entities if e["id"] not in known})
    if unknown:
        print(f"俗名表里的注册名在 rulesmd.ini 里不存在：{unknown}", file=sys.stderr)
        return 1

    DERIVED.parent.mkdir(parents=True, exist_ok=True)
    CODEX.mkdir(parents=True, exist_ok=True)
    DERIVED.write_text(dump_json(rules), encoding="utf-8")
    (CODEX / "units.md").write_text(build_units(rules, names, effects), encoding="utf-8")
    (CODEX / "buildings.md").write_text(build_buildings(rules, names, effects), encoding="utf-8")
    (CODEX / "glossary.md").write_text(build_glossary(entities, terms), encoding="utf-8")
    (CODEX / "countries.md").write_text(build_countries(rules, names, effects), encoding="utf-8")
    print(f"单位 {len(rules.units)}  建筑 {len(rules.buildings)}  "
          f"武器 {len(rules.weapons)}  弹头 {len(rules.warheads)}")
    print(f"→ {DERIVED.relative_to(REPO)}")
    missing = [u.id for u in rules.units if not is_unused(u) and u.id not in names]
    print(f"中文名 {len(names)} 条；未覆盖的可动单位 {len(missing)}：{missing}")
    problems = check_coverage(rules)
    if problems:
        for problem in problems:
            print(f"一致性检查未过：{problem}", file=sys.stderr)
        return 1
    print(f"俗名 {len(entities)} 条，战术黑话 {len(terms)} 条")
    print("→ codex/units.md  codex/buildings.md  codex/glossary.md  codex/countries.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
