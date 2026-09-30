"""可造清单：每一项要什么前提、多少钱、什么科技等级。

数据取自 `corpus/derived/rules.json`（`tools/build_codex.py` 从 `rulesmd.ini` 生成）。
引擎只告诉我们「手上有什么」，**能不能造是规则决定的**——把它算在本地，模型就不必
拿一次真金白银的废单去换引擎那句 `unbuildable object_type {...}`（实测两个测试员
都为此白花过 call 与帧）。

前提里的 `POWER` / `PROC` / `Barracks` 这类词不是建筑注册名，是 `[General]` 里的
别名，见 `rulesmd.ini` 的 `PrerequisitePower=` / `PrerequisiteProc=` 等（484-490 行）。
别名写成常量：原版规则稳定，且别名指向的注册名不会随对局变。
"""
import json
import pathlib
from dataclasses import dataclass

#: `[General]` 的前提别名 → 满足它所需的建筑注册名（任一即可）。
ALIASES = {
    "power": ("GAPOWR", "NAPOWR", "NANRCT", "YAPOWR", "NAAPWR"),
    "proc": ("GAREFN", "NAREFN", "YAREFN", "SMIN"),
    "factory": ("GAWEAP", "NAWEAP", "YAWEAP"),
    "barracks": ("NAHAND", "GAPILE", "YABRCK"),
    "radar": ("GAAIRC", "NARADR", "AMRADR", "NAPSIS"),
    "tech": ("GATECH", "NATECH", "YATECH"),
}

#: 一组里最多列几项。目录有五百多条，全给只会把上下文淹掉。
#: 名字**刻意与 `command.MAX_LISTED_UNITS` 区分**：那个是「单位清单最多列几行」，
#: 是两个数；同名过一次，读源码的人被误导过。
MAX_BUILDABLE_BUILDINGS = 10
MAX_BUILDABLE_UNITS = 8

#: 窃取科技：INI 里的旗标 → （`House` 上的标记字段，给模型看的说法）。
STOLEN_TECH = {
    "allied": ("allied_infiltrated", "窃取盟军科技"),
    "soviet": ("soviet_infiltrated", "窃取苏军科技"),
    "third": ("third_infiltrated", "窃取尤里科技"),
}

#: 判断「基地附近有没有水面」的搜索半径（格）。与建筑键 `Adjacent=12` 同量级。
WATER_NEAR_RADIUS = 12


def stolen_labels(house) -> frozenset:
    """己方**已经偷到**哪几方科技。`House` 上有现成的渗透标记。"""
    if house is None:
        return frozenset()
    return frozenset(label for field, label in STOLEN_TECH.values()
                     if getattr(house, field, False))


def stolen_label(side) -> str:
    """某一方科技的给模型看的说法。"""
    found = STOLEN_TECH.get(side)
    return found[1] if found else "窃取科技"


def all_stolen_labels() -> frozenset:
    """三方科技的标签全集。

    只用于「可达性」判断：偷没偷到是**当前状态**，不该决定一条分支算不算我们的
    科技树——否则超时空突击队这类会整条从清单里消失，模型根本学不到它存在。
    """
    return frozenset(label for _, label in STOLEN_TECH.values())


def own_building_cells(state) -> tuple:
    """己方已在地图上的建筑所在格。临水判断拿它当中心。"""
    if state is None:
        return ()
    return tuple(obj.coordinates.cell for obj in state.own_objects()
                 if obj.is_building and not obj.in_limbo)


def water_nearby(map_data, centers, *, radius=WATER_NEAR_RADIUS):
    """基地附近有没有水面。**判不了时给 `None`**（宁可不说，也不误报）。

    临水建筑（`WaterBound=yes`，船厂那类）能不能造由引擎按地形定；离线只能用这条
    近似：己方建筑周围 `radius` 格内有水就算有。
    """
    from ..constants import LandType
    if map_data is None or not centers:
        return None
    for base_x, base_y in centers:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x, y = base_x + dx, base_y + dy
                if not map_data.in_bounds(x, y):
                    continue
                if map_data.land_type(x, y) == LandType.WATER:
                    return True
    return False


@dataclass(frozen=True)
class Entry:
    """一条可造项。`kind` 对建筑是 `building`，对单位是步兵/载具/飞行器。"""

    id: str
    name: str
    kind: str
    cost: int
    tech_level: int
    prerequisite: tuple
    owners: tuple
    #: 只有这些国家能造（`RequiredHouses`）；苏军那几种「专属」单位靠它分开。
    required_houses: tuple = ()
    #: 这些国家不能造（`ForbiddenHouses`），如盟军警犬对苏军禁用。
    forbidden_houses: tuple = ()
    #: 要偷到哪一方科技才造得了（`RequiresStolen*Tech`）；空表示不需要。
    stolen_tech: str = ""
    #: `WaterBound=yes`：只能建在水边。
    water_bound: bool = False

    @property
    def is_building(self) -> bool:
        """是不是建筑。"""
        return self.kind == "building"

    @property
    def buildable(self) -> bool:
        """是不是玩家真造得出来的东西。

        规则文件里混着大量民用道具与地图摆件（`AMMOCRAT` 弹药箱、`BLUELAMP` 路灯、
        `CARGOPLANE` 运输机），它们造价 0、`TechLevel=-1`、没有前提，不过滤就会把
        「可造」那一段整个淹掉。口径与 `tools/build_codex.py` 挑「可建造」时一致：
        建筑要 `cost > 0` 且 `TechLevel != -1`，单位要 `TechLevel >= 1`；两者合并
        就是**造价大于 0 且科技等级至少 1**。
        """
        return self.cost > 0 and self.tech_level >= 1

    def missing(self, owned, *, stolen=(), water_near=None) -> tuple:
        """还缺哪些前提。

        `owned` 是己方**已在地图上**的建筑注册名集合。别名展开成「任一即可」，
        其余按注册名精确匹配。返回的仍是原始写法（`POWER`、`GAPILE`），因为模型
        要拿它去对照 `codex/buildings.md`。

        另有两条**不在 `Prerequisite` 里**、引擎却会卡的门：

        - `stolen_tech`：要偷到某方科技（`RequiresStolen*Tech`），`stolen` 给
          己方已经偷到的标签；
        - `water_bound`：只能建在水边。`water_near=False` 才算缺，`None`（判不了）
          不算——宁可不说，也不误报。
        """
        out = []
        for token in self.prerequisite:
            allowed = ALIASES.get(token.lower())
            if allowed is None:
                if token not in owned:
                    out.append(token)
            elif not any(one in owned for one in allowed):
                out.append(token)
        if self.stolen_tech and stolen_label(self.stolen_tech) not in stolen:
            out.append(stolen_label(self.stolen_tech))
        if self.water_bound and water_near is False:
            out.append("临水（基地附近要有水面）")
        return tuple(out)

    def allowed_for(self, faction) -> bool:
        """这个国家造不造得了。

        **对建筑几乎没用**：原版建筑的 `Owner` 列了所有国家（阵营由前提链里的
        `GACNST`/`NACNST` 分开）。对单位有用——盟军单位 5 个国家、苏军 4 个；
        另外 `RequiredHouses` / `ForbiddenHouses` 才是「专属」那几种的真判据
        （尤里警犬只给 `YuriCountry`，盟军警犬对苏军禁用）。
        """
        if not faction:
            return True
        if self.required_houses and faction not in self.required_houses:
            return False
        if faction in self.forbidden_houses:
            return False
        if self.owners and faction not in self.owners:
            return False
        return True


class Catalogue:
    """一份可造目录。`load` 之外全是不碰 I/O 的纯查询。"""

    def __init__(self, entries=()):
        self.entries = tuple(entries)
        self.by_id = {entry.id: entry for entry in self.entries}
        self.by_name = {}
        for entry in self.entries:
            self.by_name.setdefault(entry.name, entry)

    def __len__(self):
        return len(self.entries)

    @classmethod
    def load(cls, path) -> "Catalogue":
        """读 `corpus/derived/rules.json`；文件不在时给空目录（不是错误）。"""
        source = pathlib.Path(path)
        if not source.exists():
            return cls(())
        data = json.loads(source.read_text(encoding="utf-8"))
        entries = []
        for item in data.get("buildings", ()):
            entries.append(_entry(item, "building"))
        for item in data.get("units", ()):
            entries.append(_entry(item, item.get("kind", "unit")))
        return cls(tuple(entry for entry in entries if entry.id and entry.name))

    def entry(self, name_or_id):
        """按注册名或显示名找一条。"""
        if not name_or_id:
            return None
        return self.by_id.get(name_or_id) or self.by_name.get(name_or_id)

    def reachable(self, owned, *, tech=None, faction=None) -> frozenset:
        """从手上的建筑出发，**造得到**的建筑注册名集合（含已有的）。

        不动点展开：一条一条试，前提能凑齐就加进集合，直到不再增长。

        这一步是「分阵营」的关键：原版建筑的 `Owner` 把十个国家都列上了，光看
        owners 分不出盟苏；真正分阵营的是前提链的根——`GACNST`（owners 只有盟军五国）
        与 `NACNST`（只有苏军四国）。所以盟军玩家推不出 `NAHAND`，`NAWALL` 也就
        跟着不可达，清单里自然不出现对方的科技树。
        """
        known = set(owned)
        changed = True
        while changed:
            changed = False
            for entry in self.entries:
                if not entry.buildable or entry.id in known:
                    continue
                if tech is not None and entry.tech_level > tech:
                    continue
                if not entry.allowed_for(faction):
                    continue
                # 可达性只看**建筑前提**：偷没偷到科技、基地旁边有没有水都是当前
                # 状态，不该让一整条分支从清单里消失。
                if not entry.missing(known, stolen=all_stolen_labels()):
                    known.add(entry.id)
                    changed = True
        return frozenset(known)

    def candidates(self, owned, *, money=None, tech=None, faction=None,
                   buildings=True, limit=None, stolen=(), water_near=None):
        """候选清单，按「缺的前提最少、其次买得起、再次**贵在前**」排序。

        只列**造得到**的（见 `reachable`）：对方阵营的科技树推不出来，就不会占
        位置。`money` 给了只影响排序与标注，不剔除——知道要攒多少钱也有用。

        「贵在前」只针对**现在就能造**的那批：大件（重工、实验室）比围墙更值得先
        看到——实测按造价升序排时，矿厂一好重工就落到第 9 位、被上限截掉。还缺前提
        的则相反，按便宜在前，让「下一步该补什么」排在超武前面。

        `stolen`（已偷到的科技标签）与 `water_near`（基地旁有没有水）参与「还缺
        什么」的计算，但不影响可达性——见 `reachable`。
        """
        known = self.reachable(owned, tech=tech, faction=faction)
        out = []
        for entry in self.entries:
            if not entry.buildable:
                continue
            if entry.is_building != buildings:
                continue
            if tech is not None and entry.tech_level > tech:
                continue
            if not entry.allowed_for(faction):
                continue
            missing = entry.missing(owned, stolen=stolen, water_near=water_near)
            if entry.missing(known, stolen=all_stolen_labels()):
                continue                      # 连可达都不是：对方或够不着的分支
            poor = money is not None and entry.cost > money
            ready = not missing
            order_cost = -entry.cost if ready else entry.cost
            # 已经有的排在还没有的后面：清单关心的是「新能力」。不倒掉已有的
            # ——再造一座电厂是正常操作，只是不该占着最前面几行。
            already = 1 if entry.id in owned else 0
            out.append((len(missing), poor, 0 if ready else 1, already,
                        order_cost, entry.id, entry, missing))
        out.sort()
        found = tuple((entry, missing) for *_, entry, missing in out)
        return found[:limit] if limit is not None else found


def owned_building_ids(state, types, catalogue) -> frozenset:
    """己方**已在地图上**的建筑注册名集合。

    引擎只给显示名（`Allied Power Plant`），目录按注册名（`GAPOWR`）说话，故经显示名
    翻一次。limbo 里那栋还没落地，不算。条件与 `status` 都用这一份实现。
    """
    if catalogue is None or state is None or types is None:
        return frozenset()
    out = set()
    for obj in state.own_objects():
        if obj.in_limbo or not obj.is_building:
            continue
        entry = catalogue.by_name.get(types.name(obj, ""))
        if entry is not None:
            out.add(entry.id)
    return frozenset(out)


def _entry(item, kind) -> Entry:
    """把一条 rules.json 记录转成 `Entry`。"""
    return Entry(
        id=str(item.get("id", "")),
        name=str(item.get("name", "")),
        kind=kind,
        cost=int(item.get("cost") or 0),
        tech_level=int(item.get("tech_level") if item.get("tech_level") is not None
                       else -1),
        prerequisite=tuple(item.get("prerequisite") or ()),
        owners=tuple(item.get("owners") or ()),
        required_houses=tuple(item.get("required_houses") or ()),
        forbidden_houses=tuple(item.get("forbidden_houses") or ()),
        stolen_tech=str(item.get("stolen_tech") or ""),
        water_bound=bool(item.get("water_bound")),
    )
