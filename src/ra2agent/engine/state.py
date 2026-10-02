"""游戏状态的解析与只读视图。

字段号取自 `proto/ra2yrproto/ra2yr.proto`。解析结果用 dataclass 而非字典，
使上层拿到类型约束。

观测模型见 `.agents/notes/引擎/命令能力测绘结果.md#观测模型`：`GetGameState` 每帧
返回对象全量，但**不含地图**；地图只在 `StorageValue` 中，须经 `ReadValue` 单独
取一次，之后再按 `cells_difference` 增量更新。
"""
from dataclasses import dataclass, field
from typing import Iterator

from ..constants import LEPTONS_PER_CELL
from ..errors import ProtocolError
from .proto import fmap, one, repeated_ints, signed64, sub
from .native_events import NativeEvent, NativeTarget, parse_native_events

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
class ActualTarget:
    """DLL 的当帧目标；仅供 Observer 投影，不直接作为 L1 目标。

    1=不可观测，2=无目标，3=合法对象；字段缺失由 None 表示。
    对象引用 RTTI=52，object_type 是 WhatAmI 的具体类型。
    """

    status: int
    reference: NativeTarget | None = None
    object_type: int | None = None
    object_pointer: int | None = None

    @property
    def native_id(self) -> int | None:
        return None if self.reference is None else self.reference.m_id & 0xFFFFFFFF

    @classmethod
    def parse(cls, blob) -> "ActualTarget":
        try:
            data = fmap(blob, strict=True)
            status = _target_scalar(data, 1)
            if status not in (1, 2, 3):
                raise ProtocolError("actual_target 状态未知或缺失")
            if status != 3:
                if any(number in data for number in (2, 3, 4)):
                    raise ProtocolError("不可观测/无目标不得携带目标引用")
                return cls(status)
            reference_blob = _target_field(data, 2, 2)
            if reference_blob is None:
                raise ProtocolError("actual_target 缺少对象引用")
            reference_data = fmap(reference_blob, strict=True)
            encoded_id = _target_scalar(reference_data, 1)
            if encoded_id is None:
                encoded_id = 0  # proto3 omits an explicitly set int32 zero.
            rtti = _target_scalar(reference_data, 2)
            if (rtti != 52 or
                    not (0 <= encoded_id <= 0xFFFFFFFF or
                         0xFFFFFFFF80000000 <= encoded_id <= 0xFFFFFFFFFFFFFFFF)):
                raise ProtocolError("actual_target 对象引用需要 Abstract RTTI/native ID")
            reference = NativeTarget.parse(reference_blob)
            kind = _target_scalar(data, 3)
            pointer = _target_scalar(data, 4)
            if kind not in (1, 2, 6, 15) or not pointer or pointer > 0xFFFFFFFF:
                raise ProtocolError("actual_target 对象类型或映射指针无效")
            return cls(status, reference, kind, pointer)
        except (IndexError, TypeError) as error:
            raise ProtocolError("actual_target 消息不完整") from error


def _target_field(data, number, wire):
    entries = data.get(number)
    if not entries:
        return None
    if len(entries) != 1 or entries[0][0] != wire:
        raise ProtocolError(f"actual_target 字段 {number} 重复或 wire 无效")
    return entries[0][1]


def _target_scalar(data, number):
    return _target_field(data, number, 0)


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
    #: 正在展开 / 正在收起。不给这两项，自动层会对正在展开的基地车重复下令。
    deploying: bool = False
    undeploying: bool = False
    # Extension v1; None means that the DLL did not provide an own native ID.
    native_id: int | None = None
    # Raw same-frame reference; Observation only exposes its stable-ID projection.
    actual_target: ActualTarget | None = field(default=None, repr=False)

    @property
    def is_building(self) -> bool:
        """对应 `AbstractType.BUILDING`。"""
        from ..constants import AbstractType
        return self.object_type == AbstractType.BUILDING

    @property
    def is_unit(self) -> bool:
        """对应 `AbstractType.UNIT`。"""
        from ..constants import AbstractType
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
    is_game_over: bool = False
    power_output: int = 0
    power_drain: int = 0
    start_credits: int = 0
    #: 三方科技被渗透。引擎只给「当前是否处于被渗透状态」，
    #: 看不出「刚刚被渗透了一次」，也看不出渗透了什么。
    allied_infiltrated: bool = False
    soviet_infiltrated: bool = False
    third_infiltrated: bool = False

    @property
    def is_low_power(self) -> bool:
        """电力是否入不敷出。"""
        return self.power_drain > self.power_output

    @property
    def is_infiltrated(self) -> bool:
        """是否正被任何一方渗透。"""
        return self.allied_infiltrated or self.soviet_infiltrated or self.third_infiltrated

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
    fields = fmap(blob, strict=True)
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
        deploying=bool(get(15)),
        undeploying=bool(get(16)),
        mission=signed64(get(18)) if get(18) >= (1 << 63) else get(18),
        in_limbo=bool(get(19)),
        on_map=bool(get(20)),
        destination=parse_coordinates(sub(blob, 17)),
        initial_owner=get(11),
        native_id=_optional_uint32(fields, 21),
        actual_target=(ActualTarget.parse(_target_field(fields, 22, 2))
                       if 22 in fields else None),
    )


def _optional_uint32(fields, number):
    entries = fields.get(number)
    if not entries:
        return None
    wire, value = entries[-1]
    if wire != 0 or not 0 <= value <= 0xFFFFFFFF:
        raise ProtocolError(f"字段 {number} 需要 uint32")
    return value


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
        is_game_over=bool(get(10)),
        power_output=get(13),
        power_drain=get(14),
        start_credits=get(6),
        allied_infiltrated=bool(get(16)),
        soviet_infiltrated=bool(get(17)),
        third_infiltrated=bool(get(18)),
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
    _native_events: tuple[NativeEvent, ...] = field(repr=False, default=())
    guard_interface_version: int = 0
    stop_interface_version: int = 0
    target_observation_version: int = 0

    def __post_init__(self):
        self._by_pointer = {o.pointer: o for o in self.objects}

    @classmethod
    def parse(cls, payload) -> "GameState":
        """解析 `GetGameState` 响应中的 `GameState` 字节。"""
        fields = fmap(payload, strict=True)
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
            _native_events=parse_native_events(fields),
            guard_interface_version=_optional_uint32(fields, 17) or 0,
            stop_interface_version=_optional_uint32(fields, 18) or 0,
            target_observation_version=_optional_uint32(fields, 19) or 0,
        )

    @property
    def native_events(self) -> tuple[NativeEvent, ...]:
        """仅当前玩家的原版输入事件，不包含对手的命令记录。

        必须存在唯一 current_player；不解析对象编码与稳定 ID 的关系，
        不提供生效确认，也不代表当前 Target / Follow 的持续状态。
        """
        index = self.player_house().array_index
        return tuple(event for event in self._native_events
                     if event.house_index == index)

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

    def tiberium_value(self, cell_x, cell_y) -> int:
        """该格的矿石量（0 即无矿）。

        「派矿车去最近的矿」只能靠它——引擎没有采矿动作，唯一的路是把矿车移到矿格
        上让游戏自身的采矿 AI 接管。
        """
        return self._column("tiberium_value", cell_x, cell_y)

    def is_explored(self, cell_x, cell_y) -> bool:
        """这一格探过了没有。侦察的目标就是**没探过**的那些格。"""
        return not self.shrouded(cell_x, cell_y)

    def is_clear(self, cell_x, cell_y) -> bool:
        """已探索且地形为 `Clear`，可作为候选移动目标。"""
        from ..constants import LandType
        return (self.in_bounds(cell_x, cell_y)
                and not self.shrouded(cell_x, cell_y)
                and self.land_type(cell_x, cell_y) == LandType.CLEAR)

    def iter_cells(self) -> Iterator[tuple[int, int]]:
        """产出全部格坐标。"""
        for y in range(self.height):
            for x in range(self.width):
                yield x, y

    def apply(self, cell: Cell) -> bool:
        """按 `Cell.index` 回填一格，返回是否落在范围内。

        用于吸收 `GameState.cells_difference`：服务端只在格子内容变化时才发送，
        且带上 `index` 与 `shrouded`，故迷雾可增量维护而不必重取整张地图。
        """
        index = cell.index
        if not 0 <= index < self.width * self.height:
            return False
        # shrouded 是永久的「已探索」标志，只允许由真变假：引擎侧 AltFlags 只
        # 置位不清除，这里同样不接受回退，以免被异常的增量重新遮蔽已探明区域。
        shrouded = self.columns.get("shrouded")
        if shrouded is not None and index < len(shrouded) and not cell.shrouded:
            shrouded[index] = 0
        for name, value in (("land_type", cell.land_type),
                            ("height", cell.height),
                            ("level", cell.level),
                            ("overlay_data", cell.overlay_data),
                            ("tiberium_value", cell.tiberium_value),
                            ("passability", cell.passability)):
            column = self.columns.get(name)
            if column is not None and index < len(column):
                column[index] = value
        return True

    def apply_all(self, cells) -> int:
        """回填一批格，返回实际生效的数量。"""
        return sum(1 for cell in cells if self.apply(cell))


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

    def __init__(self, entries=(), aliases=None):
        self.by_pointer: dict[int, ObjectType] = {}
        self.by_key: dict[tuple[int, int], ObjectType] = {}
        for entry in entries:
            self.by_pointer[entry.pointer] = entry
            self.by_key.setdefault((entry.type, entry.array_index), entry)
        #: 注册名（`MTNK` 一类）到指针。引擎只给显示名，故这张表由外面填。
        self.aliases: dict[str, int] = {k.lower(): v for k, v in (aliases or {}).items()}

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

    def add_aliases(self, mapping) -> int:
        """补上注册名到指针的对照，返回新增了几条。大小写不敏感。"""
        before = len(self.aliases)
        self.aliases.update({str(k).lower(): v for k, v in mapping.items()})
        return len(self.aliases) - before

    def resolve(self, needle, rtti=None) -> ObjectType | None:
        """按注册名、显示名或子串解析类型。注册名要有人填过 `aliases` 才认得出。

        顺序是「注册名 → 显示名全等 → 子串」：越精确的越先试，免得 `E1` 这类短名字
        被别的类型先抢走。
        """
        if not needle:
            return None
        text = str(needle).strip()
        by_alias = self.aliases.get(text.lower())
        if by_alias is not None:
            found = self.by_pointer.get(by_alias)
            if found is not None and (rtti is None or found.type == rtti):
                return found
        lowered = text.lower()
        for entry in self.by_pointer.values():
            if rtti is not None and entry.type != rtti:
                continue
            if entry.name.lower() == lowered:
                return entry
        return self.find(text, rtti)

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
