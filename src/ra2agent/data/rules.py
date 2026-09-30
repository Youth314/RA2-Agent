"""读原版 `rulesmd.ini`，产出单位 / 建筑 / 武器 / 弹头的结构化表。

只做解析与索引，不做判断、不联网。原始文件不入库，见 `corpus/README.md`。

两处**不在 INI 里**、由引擎硬编码的东西：

- **装甲类型的顺序。** 弹头用 `Verses=25%,25%,15%,...` 给 11 个百分比，但那 11 个位置
  分别是什么装甲，INI 里没有（没有 `[ArmorTypes]` 节）。出处是 ModEnc 的 `Verses` 页。
- **武器的清单。** 没有 `[Weapons]` 节，武器只能从单位与建筑的 `Primary=` /
  `Secondary=` 反查。

故本模块顺着引用走一遍，只收**可达的**武器与弹头。
"""
import re
from dataclasses import dataclass, field

#: 引擎硬编码的装甲顺序，对应弹头 `Verses=` 的 11 个百分比。
#: 出处：ModEnc 的 `Verses` 页（`corpus/raw/modenc/pages.jsonl`）。
ARMOR_TYPES = ("none", "flak", "plate", "light", "medium", "heavy",
               "wood", "steel", "concrete", "special_1", "special_2")

#: `[Countries]` 里的引擎占位项，不是可选国家。
PLACEHOLDER_COUNTRIES = frozenset({"GDI", "Nod", "Neutral", "Special"})

#: 单位的三个来源节，按此顺序读。
UNIT_SECTIONS = (("infantry", "InfantryTypes"),
                 ("vehicle", "VehicleTypes"),
                 ("aircraft", "AircraftTypes"))

#: 建筑上对决策有意义的旗标，映射成人话标签。
BUILDING_FLAGS = (
    ("SecretLab", "secret_lab"),
    ("UnitRepair", "repairs_units"),
    ("Refinery", "refinery"),
    ("ResourceGatherer", "harvester"),
    ("SpySat", "spy_satellite"),
    ("PowersUnit", "powers_unit"),
    ("Unsellable", "cannot_sell"),
)

_TRUE = frozenset({"yes", "true", "1"})
_SECTION = re.compile(r"^\[([^\]]+)\]\s*$")


def strip_comment(line):
    """去掉 INI 注释（`;` 与 `//`）并去空白。

    **`//` 也是原版 `rulesmd.ini` 的注释写法**，不能只认分号：`[MirageWH]` 那个节头
    就写成 `[MirageWH]\t// Supposed to be a heat ray.`。只认分号时这一行匹配不上
    节头正则，整节（含 `Verses=`）被并进上一节——幻影坦克的武器伤害因此一路缺到
    `codex/units.md`，测试员只能回原始 ini 手查。
    """
    cut = len(line)
    for mark in (";", "//"):
        found = line.find(mark)
        if found != -1:
            cut = min(cut, found)
    return line[:cut].strip()


def as_bool(value, default=False):
    """RA2 的布尔写法不统一：`yes` / `true` / `1` 都算真。"""
    if value is None:
        return default
    return value.strip().lower() in _TRUE


def as_int(value, default=0):
    """取整数；取不到给默认值。"""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def as_list(value):
    """逗号分隔的清单。"""
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


#: 窃取科技的三方。键是 INI 里的旗标，值是给模型看的说法。
STOLEN_TECH_KEYS = (("allied", "RequiresStolenAlliedTech"),
                    ("soviet", "RequiresStolenSovietTech"),
                    ("third", "RequiresStolenThirdTech"))


def stolen_tech_of(data) -> str:
    """这条单位/建筑要偷到哪一方的科技才造得了；不需要则给空串。

    引擎会拿它当额外门（实测：超时空突击队 `RequiresStolenAlliedTech=yes`，
    光看 `Prerequisite=BARRACKS` 判成「现在就能造」，下单后被 `unbuildable` 拒）。
    """
    for side, key in STOLEN_TECH_KEYS:
        if as_bool(data.get(key)):
            return side
    return ""


def load_sections(text):
    """把 INI 读成 `{节名: {键: 值}}`，节名按出现顺序。"""
    sections = {}
    current = None
    for raw in text.splitlines():
        line = strip_comment(raw)
        if not line:
            continue
        match = _SECTION.match(line)
        if match:
            current = match.group(1).strip()
            sections.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            continue
        key, _, value = line.partition("=")
        sections[current][key.strip()] = value.strip()
    return sections


def parse_verses(value):
    """把 `Verses=25%,25%,...` 读成百分比整数元组，顺序即 `ARMOR_TYPES`。"""
    if not value:
        return ()
    return tuple(as_int(part.strip().rstrip("%"))
                 for part in value.split(",") if part.strip())


def collect_ids(sections, section_name):
    """读 `[XxxTypes]` 这类清单节。值可能是单个 id，也可能是逗号清单。"""
    out = []
    for value in sections.get(section_name, {}).values():
        for identifier in as_list(value):
            if identifier not in out:
                out.append(identifier)
    return out


def load_ids_by_name(path):
    """从 `corpus/derived/rules.json` 读「显示名 → 注册名」。

    引擎的类型表只给显示名（`Grizzly Battle Tank`），而技法与文档都按注册名
    （`MTNK`）说话。文件不存在时返回空——别名只是便利，不是必需。
    """
    import json
    import pathlib

    source = pathlib.Path(path)
    if not source.exists():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    out = {}
    for group in ("units", "buildings"):
        for item in data.get(group, ()):
            out.setdefault(item.get("name", ""), item.get("id", ""))
    out.pop("", None)
    return out


def attach_type_aliases(types, path):
    """把注册名挂到引擎的类型表上。返回挂上了几条。

    靠显示名对上——同一个显示名对应多个注册名时（民用、地图道具那几组），
    谁先到算谁。可建造的单位与建筑显示名是唯一的，故不影响它们。
    """
    ids = load_ids_by_name(path)
    if not ids:
        return 0
    mapping = {}
    for entry in types.by_pointer.values():
        identifier = ids.get(entry.name)
        if identifier:
            mapping[identifier] = entry.pointer
    return types.add_aliases(mapping)


@dataclass(frozen=True)
class Country:
    """一个可用国家。`side` 是阵营，`display` 是游戏里显示的名字。"""

    id: str
    side: str
    display: str

    @property
    def playable(self):
        """能选的国家。

        `[Countries]` 列了 14 项，其中 4 项是引擎占位：`GDI` 与 `Nod` 的 `Name`
        就等于自己的 id（真正的国家另有其名，如 `Americans` 的 `Name=America`），
        `Neutral` 与 `Special` 是中立与任务方。故选得到的只有 10 个。
        """
        return (self.id not in PLACEHOLDER_COUNTRIES
                and self.side in ("GDI", "Nod", "ThirdSide"))


@dataclass(frozen=True)
class Weapon:
    """一个武器节。`rof` 是两次开火的间隔帧数。"""

    id: str
    damage: int
    rof: int
    rng: float
    warhead: str
    projectile: str
    burst: int = 1

    @property
    def dps(self):
        """每帧伤害（单发，不含弹头倍率）。"""
        return self.damage * self.burst / self.rof if self.rof else 0.0


@dataclass(frozen=True)
class Warhead:
    """一个弹头节。`verses` 是 11 种装甲的伤害倍率百分比。"""

    id: str
    verses: tuple

    def multiplier(self, armor, armor_types=ARMOR_TYPES):
        """对某种装甲的倍率（1.0 为满伤）。装甲名不认识或没写这一位时给 1.0。"""
        try:
            index = armor_types.index(armor.lower())
        except (ValueError, AttributeError):
            return 1.0
        if index >= len(self.verses):
            return 1.0
        return self.verses[index] / 100.0


@dataclass(frozen=True)
class UnitType:
    """一个可动单位：步兵、载具或飞行器。"""

    id: str
    name: str
    kind: str
    cost: int
    strength: int
    armor: str
    speed: int
    sight: int
    tech_level: int
    prerequisite: tuple
    owners: tuple
    primary: str = ""
    secondary: str = ""
    passengers: int = 0
    #: 只有这些阵营能造；空表示不设限。
    required_houses: tuple = ()
    #: 这些阵营不能造；空表示不设限。
    forbidden_houses: tuple = ()
    #: 要偷到哪一方科技才造得了（`RequiresStolen*Tech`）；空表示不需要。
    stolen_tech: str = ""
    #: `Harvester=yes`：矿车。**认出它才管得住它**——被 `STOP` 过的矿车不会自己
    #: 恢复采矿（实测整局资金停在 100），而引擎没有采矿动作，只能把它移回矿格让
    #: 游戏自身的采矿 AI 接管。
    harvester: bool = False


@dataclass(frozen=True)
class BuildingType:
    """一个建筑。`special` 是从旗标推出的人话标签。"""

    id: str
    name: str
    cost: int
    strength: int
    armor: str
    power: int
    tech_level: int
    prerequisite: tuple
    owners: tuple
    capturable: bool = False
    can_be_occupied: bool = False
    max_occupants: int = 0
    special: tuple = ()
    foundation: str = ""
    primary: str = ""
    secondary: str = ""
    required_houses: tuple = ()
    forbidden_houses: tuple = ()
    #: `WaterBound=yes`：只能建在水边（船厂那类）。能不能造由引擎按地形判。
    water_bound: bool = False


@dataclass
class Rules:
    """一份解析好的 `rulesmd.ini`。"""

    units: tuple = ()
    buildings: tuple = ()
    weapons: dict = field(default_factory=dict)
    warheads: dict = field(default_factory=dict)
    #: 国家 id → `Country`。阵营从各国家节的 `Side=` 读，不写死在代码里。
    countries: dict = field(default_factory=dict)

    def sides(self):
        """阵营 → 属于它的国家 id 元组。"""
        out = {}
        for country in self.countries.values():
            out.setdefault(country.side, []).append(country.id)
        return {side: tuple(sorted(ids)) for side, ids in out.items()}

    def unit(self, identifier):
        """按 id 找单位。"""
        return next((u for u in self.units if u.id == identifier), None)

    def building(self, identifier):
        """按 id 找建筑。"""
        return next((b for b in self.buildings if b.id == identifier), None)

    def damage_per_shot(self, attacker, defender):
        """一次开火对某个防御者的伤害；算不出来返回 `None`。

        走 武器 → 弹头 → `Verses` 三步，缺任何一步都算不出来。
        """
        weapon = self.weapons.get(getattr(attacker, "primary", ""))
        if weapon is None:
            return None
        warhead = self.warheads.get(weapon.warhead)
        if warhead is None:
            return None
        return weapon.damage * warhead.multiplier(defender.armor)


def _parse_weapon(sections, weapon_id):
    """读一个武器节；没有这一节返回 `None`。"""
    data = sections.get(weapon_id)
    if data is None:
        return None
    return Weapon(
        id=weapon_id,
        damage=as_int(data.get("Damage")),
        rof=as_int(data.get("ROF"), 1) or 1,
        rng=float(as_int(data.get("Range"))),
        warhead=data.get("Warhead", ""),
        projectile=data.get("Projectile", ""),
        burst=as_int(data.get("Burst"), 1) or 1,
    )


def _building_special(data):
    """从建筑旗标推出人话标签。"""
    special = [label for key, label in BUILDING_FLAGS if as_bool(data.get(key))]
    if as_int(data.get("NumberOfDocks")) > 0:
        special.append("naval_dock")
    if as_int(data.get("ExtraPower")):
        special.append("extra_power")
    return tuple(special)


def parse_rules(text):
    """把 `rulesmd.ini` 解析成 `Rules`。"""
    sections = load_sections(text)
    owners_of = lambda data: as_list(data.get("Owner") or data.get("Owners"))  # noqa: E731
    required_of = lambda data: as_list(data.get("RequiredHouses"))             # noqa: E731
    forbidden_of = lambda data: as_list(data.get("ForbiddenHouses"))           # noqa: E731

    units, buildings, holders = [], [], []
    for kind, section_name in UNIT_SECTIONS:
        for identifier in collect_ids(sections, section_name):
            data = sections.get(identifier)
            if not data:
                continue
            units.append(UnitType(
                id=identifier, name=data.get("Name", identifier), kind=kind,
                cost=as_int(data.get("Cost")), strength=as_int(data.get("Strength")),
                armor=data.get("Armor", "none"), speed=as_int(data.get("Speed")),
                sight=as_int(data.get("Sight")),
                tech_level=as_int(data.get("TechLevel"), -1),
                prerequisite=as_list(data.get("Prerequisite")), owners=owners_of(data),
                primary=data.get("Primary", ""), secondary=data.get("Secondary", ""),
                passengers=as_int(data.get("Passengers")),
                required_houses=required_of(data), forbidden_houses=forbidden_of(data),
                stolen_tech=stolen_tech_of(data),
                harvester=as_bool(data.get("Harvester"))))
            holders.append((data.get("Primary", ""), data.get("Secondary", "")))

    for identifier in collect_ids(sections, "BuildingTypes"):
        data = sections.get(identifier)
        if not data:
            continue
        buildings.append(BuildingType(
            id=identifier, name=data.get("Name", identifier),
            cost=as_int(data.get("Cost")), strength=as_int(data.get("Strength")),
            armor=data.get("Armor", "none"), power=as_int(data.get("Power")),
            tech_level=as_int(data.get("TechLevel"), -1),
            prerequisite=as_list(data.get("Prerequisite")), owners=owners_of(data),
            capturable=as_bool(data.get("Capturable")),
            can_be_occupied=as_bool(data.get("CanBeOccupied")),
            max_occupants=as_int(data.get("MaxNumberOccupants")),
            special=_building_special(data), foundation=data.get("Foundation", ""),
            primary=data.get("Primary", ""), secondary=data.get("Secondary", ""),
            required_houses=required_of(data), forbidden_houses=forbidden_of(data),
            water_bound=as_bool(data.get("WaterBound"))))
        holders.append((data.get("Primary", ""), data.get("Secondary", "")))

    weapons, warheads = {}, {}
    for primary, secondary in holders:
        for weapon_id in (primary, secondary):
            if weapon_id and weapon_id not in weapons:
                weapon = _parse_weapon(sections, weapon_id)
                if weapon is not None:
                    weapons[weapon_id] = weapon
    for weapon in weapons.values():
        data = sections.get(weapon.warhead)
        if weapon.warhead and data is not None and weapon.warhead not in warheads:
            warheads[weapon.warhead] = Warhead(id=weapon.warhead,
                                               verses=parse_verses(data.get("Verses")))

    countries = {}
    for identifier in collect_ids(sections, "Countries"):
        data = sections.get(identifier)
        if data:
            countries[identifier] = Country(id=identifier, side=data.get("Side", ""),
                                            display=data.get("Name", identifier))

    return Rules(units=tuple(units), buildings=tuple(buildings),
                 weapons=weapons, warheads=warheads, countries=countries)
