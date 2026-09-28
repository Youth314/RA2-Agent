"""游戏状态的解析与只读视图。

字段号取自 `proto/ra2yrproto/ra2yr.proto`。解析结果用 dataclass 而非字典，
使上层拿到类型约束。

观测模型见 `.agents/notes/命令能力测绘结果.md#观测模型`：`GetGameState` 每帧
返回对象全量，但**不含地图**；地图只在 `StorageValue` 中，须经 `ReadValue` 单独
取一次，之后再按 `cells_difference` 增量更新。
"""
from dataclasses import dataclass, field
from typing import Iterator

from .constants import LEPTONS_PER_CELL
from .errors import ProtocolError
from .proto import fmap, one, repeated_ints, signed64, sub

# ---------------------------------------------------------------- 基础类型
@dataclass(frozen=True)
class Coordinates:
    """世界坐标，单位为 lepton。一格为 `LEPTONS_PER_CELL` 个 lepton。"""

    x: int = 0
    y: int = 0
    z: int = 0

    @classmethod
    def parse(cls, blob) -> "Coordinates":
        """解析 `Coordinates`。"""
        fields = fmap(blob)
        get = lambda f: fields.get(f, [(0, 0)])[0][1]  # noqa: E731
        return cls(get(1), get(2), get(3))

    @property
    def cell(self) -> tuple[int, int]:
        """所属格坐标。复现 `CellClass::Coord2Cell`：向零截断后除以 256。"""
        return _trunc_div(self.x, LEPTONS_PER_CELL), \
            _trunc_div(self.y, LEPTONS_PER_CELL)


def _trunc_div(a, b):
    """C++ 整数除法向零截断，与 Python 的向下取整不同。"""
    quotient = abs(a) // abs(b)
    return -quotient if (a < 0) != (b < 0) else quotient


def cell_center(cell_x, cell_y, z=0) -> Coordinates:
    """格中心的世界坐标。对应 YRpp `CellClass::Cell2Coord`。"""
    return Coordinates(cell_x * LEPTONS_PER_CELL + LEPTONS_PER_CELL // 2,
                       cell_y * LEPTONS_PER_CELL + LEPTONS_PER_CELL // 2, z)


def parse_coordinates(blob) -> Coordinates:
    """解析 `Coordinates`。"""
    fields = fmap(blob)
    get = lambda f: fields.get(f, [(0, 0)])[0][1]  # noqa: E731
    return Coordinates(get(1), get(2), get(3))


# ---------------------------------------------------------------- 实体
@dataclass(frozen=True)
class GameObject:
    """`Object`。字段名沿用 proto，便于对照。"""

    pointer: int
    type_pointer: int
    health: int
    coordinates: Coordinates
    house: int
    array_index: int
    object_type: int
    selected: bool
    deployed: bool
    mission: int
    in_limbo: bool
    on_map: bool
    destination: Coordinates
    initial_owner: int

    @property
    def is_building(self) -> bool:
        """对应 `AbstractType.BUILDING`。"""
        from .constants import AbstractType
        return self.object_type == AbstractType.BUILDING

    @property
    def is_unit(self) -> bool:
        """对应 `AbstractType.UNIT`。"""
        from .constants import AbstractType
        return self.object_type == AbstractType.UNIT


@dataclass(frozen=True)
class House:
    """`House`。"""

    pointer: int
    array_index: int
    name: str
    faction: str
    money: int
    current_player: bool
    is_human_player: bool
    defeated: bool
    is_winner: bool
    is_loser: bool

    @property
    def is_neutral(self) -> bool:
        """中立与特殊阵营不接受指挥，也不应计入敌方。"""
        return self.faction in ("Neutral", "Special")


@dataclass(frozen=True)
class Factory:
    """`Factory`。`progress_timer` 走到 `PRODUCTION_STEPS` 即完工。"""

    progress_timer: int
    owner: int
    object: int
    queued_objects: tuple[int, ...]
    on_hold: bool
    completed: bool


@dataclass(frozen=True)
class Cell:
    """`Cell`。`shrouded` 是永久的「已探索」标志，见测绘结果。"""

    index: int
    land_type: int
    shrouded: bool
    height: int
    level: int
    overlay_data: int
    tiberium_value: int
    passability: int
    objects: tuple[int, ...] = ()


def parse_object(blob) -> GameObject:
    """解析 `Object`。"""
    fields = fmap(blob)
    get = lambda f, d=0: fields.get(f, [(0, d)])[0][1]  # noqa: E731
    return GameObject(
        pointer=get(10),
        type_pointer=get(1),
        health=get(2),
        coordinates=parse_coordinates(sub(blob, 3)),
        house=get(4),
        array_index=get(8),
        object_type=get(9),
        selected=bool(get(13)),
        deployed=bool(get(14)),
        mission=signed64(get(18)) if get(18) >= (1 << 63) else get(18),
        in_limbo=bool(get(19)),
        on_map=bool(get(20)),
        destination=parse_coordinates(sub(blob, 17)),
        initial_owner=get(11),
    )


def parse_house(blob) -> House:
    """解析 `House`。"""
    fields = fmap(blob)
    get = lambda f, d=0: fields.get(f, [(0, d)])[0][1]  # noqa: E731

    def text(f):
        value = get(f, b"")
        return value.decode(errors="replace") if isinstance(value, bytes) else str(value)

    return House(
        pointer=get(8),
        array_index=get(1),
        name=text(2),
        faction=text(3),
        money=get(7),
        current_player=bool(get(5)),
        is_human_player=bool(get(19)),
        defeated=bool(get(4)),
        is_winner=bool(get(11)),
        is_loser=bool(get(12)),
    )


def parse_factory(blob) -> Factory:
    """解析 `Factory`。"""
    fields = fmap(blob)
    get = lambda f, d=0: fields.get(f, [(0, d)])[0][1]  # noqa: E731
    return Factory(
        progress_timer=get(1),
        owner=get(2),
        object=get(3),
        queued_objects=tuple(repeated_ints(fields.get(4, []))),
        on_hold=bool(get(5)),
        completed=bool(get(6)),
    )


def parse_cell(blob) -> Cell:
    """解析 `Cell`。"""
    fields = fmap(blob)
    get = lambda f, d=0: fields.get(f, [(0, d)])[0][1]  # noqa: E731
    objects = []
    for _, value in fields.get(8, []):
        objects.append(one(value, 10, 0))
    return Cell(
        index=get(13),
        land_type=get(1),
        shrouded=bool(get(9)),
        height=get(3),
        level=get(4),
        overlay_data=get(5),
        tiberium_value=get(6),
        passability=get(10),
        objects=tuple(objects),
    )


# ---------------------------------------------------------------- 一帧观测
@dataclass
class GameState:
    """一帧 `GameState`。构造后字段只读。"""

    frame: int
    stage: int
    tech_level: int
    crc: int
    houses: tuple[House, ...]
    objects: tuple[GameObject, ...]
    factories: tuple[Factory, ...]
    cells_difference: tuple[Cell, ...]
    raw: bytes = field(repr=False, default=b"")
    _by_pointer: dict = field(repr=False, default_factory=dict)

    def __post_init__(self):
        self._by_pointer = {o.pointer: o for o in self.objects}

    @classmethod
    def parse(cls, payload) -> "GameState":
        """解析 `GetGameState` 响应中的 `GameState` 字节。"""
        fields = fmap(payload)
        return cls(
            frame=one(payload, 1, 0),
            stage=one(payload, 7, 0),
            tech_level=one(payload, 14, 0),
            crc=one(payload, 16, 0),
            houses=tuple(parse_house(v) for _, v in fields.get(4, [])),
            objects=tuple(parse_object(v) for _, v in fields.get(6, [])),
            factories=tuple(parse_factory(v) for _, v in fields.get(3, [])),
            cells_difference=tuple(parse_cell(v) for _, v in fields.get(15, [])),
            raw=bytes(payload),
        )

    def object(self, pointer) -> GameObject | None:
        """按引擎指针查找对象；不存在返回 `None`。"""
        return self._by_pointer.get(pointer)

    def require_object(self, pointer) -> GameObject:
        """按引擎指针查找对象；不存在抛 `ProtocolError`。"""
        found = self._by_pointer.get(pointer)
        if found is None:
            raise ProtocolError(f"对象 {pointer} 不在当前状态中")
        return found

    def player_house(self) -> House:
        """本进程所控制的阵营。

        以 `current_player` 判定，并断言恰好有一个：为 0 或大于 1 说明席位
        假设不成立，此时报错而非猜测。
        """
        mine = [h for h in self.houses if h.current_player]
        if len(mine) != 1:
            raise ProtocolError(
                f"期望恰好一个 current_player 阵营，实际 {len(mine)} 个")
        return mine[0]

    def own_objects(self) -> list[GameObject]:
        """己方全部对象，含处于 limbo 者。"""
        mine = self.player_house()
        return [o for o in self.objects if o.house == mine.pointer]

    def own_factories(self) -> list[Factory]:
        """己方的生产队列。"""
        mine = self.player_house()
        return [f for f in self.factories if f.owner == mine.pointer]

    def enemy_houses(self) -> list[House]:
        """除己方、中立与特殊之外的阵营。"""
        mine = self.player_house()
        return [h for h in self.houses
                if h.pointer != mine.pointer and not h.is_neutral]


# ---------------------------------------------------------------- 地图
@dataclass
class MapData:
    """`ReadValue{map_data_soa}` 的结果。

    结构数组形式，各列等长，按行主序排列：`index = y * width + x`。
    """

    width: int
    height: int
    columns: dict
    raw: bytes = field(repr=False, default=b"")

    #: 列名到 `MapDataSoA` 字段号的映射
    FIELDS = {1: "land_type", 2: "radiation_level", 3: "height", 4: "level",
              5: "overlay_data", 6: "tiberium_value", 7: "shrouded",
              8: "passability"}

    @classmethod
    def parse(cls, read_value_payload) -> "MapData":
        """解析 `ReadValue` 响应中 `StorageValue.map_data_soa` 的字节。"""
        storage = sub(read_value_payload, 1)
        soa = sub(storage, 5)
        fields = fmap(soa)
        columns = {}
        for number, name in cls.FIELDS.items():
            entries = fields.get(number, [])
            values = []
            for wire, value in entries:
                if wire == 0:
                    values.append(value)
                elif wire == 2:
                    from .proto import packed_varints
                    values.extend(packed_varints(value))
            columns[name] = values
        return cls(width=one(soa, 9, 0), height=one(soa, 10, 0),
                   columns=columns, raw=bytes(soa))

    @property
    def cell_count(self) -> int:
        """格总数，应为 `width * height`。"""
        return len(self.columns.get("shrouded", ()))

    def in_bounds(self, cell_x, cell_y) -> bool:
        """格坐标是否在地图内。"""
        return 0 <= cell_x < self.width and 0 <= cell_y < self.height

    def cell_index(self, cell_x, cell_y) -> int:
        """格坐标转行主序下标。"""
        return cell_y * self.width + cell_x

    def _column(self, name, cell_x, cell_y, default=0):
        values = self.columns.get(name)
        if not values:
            return default
        index = self.cell_index(cell_x, cell_y)
        return values[index] if index < len(values) else default

    def shrouded(self, cell_x, cell_y) -> bool:
        """该格是否未曾探索。

        `spawn.ini` 置 `FogOfWar=No` 时引擎只有未探索与可见两态，故此值即
        精确的可见性。详见测绘结果。
        """
        return bool(self._column("shrouded", cell_x, cell_y, 1))

    def land_type(self, cell_x, cell_y) -> int:
        """该格地形。"""
        return self._column("land_type", cell_x, cell_y)

    def passability(self, cell_x, cell_y) -> int:
        """该格通行标志位。"""
        return self._column("passability", cell_x, cell_y)

    def is_clear(self, cell_x, cell_y) -> bool:
        """已探索且地形为 `Clear`，可作为候选移动目标。"""
        from .constants import LandType
        return (self.in_bounds(cell_x, cell_y)
                and not self.shrouded(cell_x, cell_y)
                and self.land_type(cell_x, cell_y) == LandType.CLEAR)

    def iter_cells(self) -> Iterator[tuple[int, int]]:
        """产出全部格坐标。"""
        for y in range(self.height):
            for x in range(self.width):
                yield x, y


# ---------------------------------------------------------------- 类型表
@dataclass(frozen=True)
class ObjectType:
    """`ObjectTypeClass` 的一个条目。"""

    name: str
    cost: int
    array_index: int
    pointer: int
    type: int


class TypeTable:
    """对象类型表。

    类型表只在首帧的 `GameState.object_types` 中下发，连晚了取不到，因此经
    `ReadValue{initial_game_state}` 单独取一次。对象经 `type_pointer` 关联到此表。
    """

    def __init__(self, entries=()):
        self.by_pointer: dict[int, ObjectType] = {}
        self.by_key: dict[tuple[int, int], ObjectType] = {}
        for entry in entries:
            self.by_pointer[entry.pointer] = entry
            self.by_key.setdefault((entry.type, entry.array_index), entry)

    @classmethod
    def parse(cls, read_value_payload) -> "TypeTable":
        """解析 `ReadValue{initial_game_state}` 的响应。"""
        initial = sub(sub(read_value_payload, 1), 3)
        entries = []
        for _, blob in fmap(initial).get(5, []):
            fields = fmap(blob)
            get = lambda f, d=0: fields.get(f, [(0, d)])[0][1]  # noqa: E731
            name = get(1, b"")
            entries.append(ObjectType(
                name=name.decode(errors="replace") if isinstance(name, bytes) else str(name),
                cost=get(2),
                array_index=get(5),
                pointer=get(6),
                type=get(9),
            ))
        return cls(entries)

    def __len__(self):
        return len(self.by_pointer)

    def info(self, obj) -> ObjectType | None:
        """按 `GameObject` 或 `pointer_technotypeclass` 查类型。"""
        pointer = obj.type_pointer if isinstance(obj, GameObject) else obj
        return self.by_pointer.get(pointer)

    def name(self, obj, default="?") -> str:
        """按对象查显示名。"""
        found = self.info(obj)
        return found.name if found and found.name else default

    def find(self, needle, rtti=None) -> ObjectType | None:
        """按名字子串查找类型。

        传入 `rtti` 可限定种类，例如 `AbstractType.BUILDINGTYPE`。
        """
        lowered = needle.lower()
        for entry in self.by_pointer.values():
            if rtti is not None and entry.type != rtti:
                continue
            if lowered in entry.name.lower():
                return entry
        return None
