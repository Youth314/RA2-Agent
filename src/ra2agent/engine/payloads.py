"""协议消息的构造。

字段号取自 `proto/ra2yrproto/`。每个函数返回可直接发送的载荷字节，不含
`Any` 包装与命令类型——那两样由 `client.Client` 补上。

设计上刻意只暴露服务端真正读取的字段，避免传入被忽略的参数造成误解。例如
`produce_order` 不接受 action，因为服务端从不读取它。
"""
from ..constants import LEPTONS_PER_CELL, PLACE_QUERY_MAX_LENGTH, UnitAction
from .proto import pb_bytes, pb_str, pb_uint
from .state import Coordinates, GameObject, ObjectType


def coordinates_payload(coordinates: Coordinates) -> bytes:
    """`Coordinates{1: x, 2: y, 3: z}`。"""
    return (pb_uint(1, coordinates.x) + pb_uint(2, coordinates.y)
            + pb_uint(3, coordinates.z))


# ---------------------------------------------------------------- 单位指令
def unit_order(units, action: UnitAction, target_object=None,
               coordinates: Coordinates | None = None) -> bytes:
    """`UnitOrder{object_addresses, action, target_object, coordinates}`。"""
    out = b"".join(pb_uint(1, _pointer_of(u)) for u in units)
    out += pb_uint(2, int(action))
    if target_object:
        out += pb_uint(3, _pointer_of(target_object))
    if coordinates is not None:
        out += pb_bytes(4, coordinates_payload(coordinates))
    return out


def guard_order(pointer, action, native_id, house_pointer, basis_frame,
                coordinates=None) -> bytes:
    """Controlled UnitOrder extension v1; no target objects or arbitrary missions."""
    from ..errors import InvalidCommand

    if action not in (UnitAction.GUARD_CURRENT, UnitAction.GUARD_POSITION):
        raise InvalidCommand("不是受控 Guard 操作")
    if (action == UnitAction.GUARD_CURRENT) != (coordinates is None):
        raise InvalidCommand("Guard 目标类别不匹配")
    return _controlled_order(pointer, action, native_id, house_pointer, basis_frame, coordinates)


def stop_order(pointer, native_id, house_pointer, basis_frame) -> bytes:
    """L0-only player Stop; no target or arbitrary action argument."""
    return _controlled_order(pointer, UnitAction.PLAYER_STOP, native_id, house_pointer, basis_frame)


def _controlled_order(pointer, action, native_id, house_pointer, basis_frame, coordinates=None):
    from ..errors import InvalidCommand

    for label, value in (("pointer", pointer), ("native_id", native_id),
                         ("house_pointer", house_pointer)):
        if type(value) is not int or not 0 < value <= 0xFFFFFFFF:
            raise InvalidCommand(f"受控操作 {label} 需要非零 uint32")
    if type(basis_frame) is not int or not 0 <= basis_frame <= 0xFFFFFFFF:
        raise InvalidCommand("受控操作 basis_frame 需要 uint32")
    return (unit_order((pointer,), action, coordinates=coordinates)
            + pb_uint(5, native_id) + pb_uint(6, house_pointer)
            + pb_uint(7, basis_frame))


def attack_target_order(pointer, native_id, house_pointer, basis_frame,
                        target, target_native_id, target_house, target_type):
    """L0-only Attack v1; a pinned object target, no cell or Mission argument."""
    from ..errors import InvalidCommand

    for label, value in (("target", target), ("target_native_id", target_native_id),
                         ("target_house", target_house)):
        if type(value) is not int or not 0 < value <= 0xFFFFFFFF:
            raise InvalidCommand(f"Attack {label} 需要非零 uint32")
    if type(target_type) is not int or target_type not in (1, 6):
        raise InvalidCommand("unsupported: Attack 目标只接受车辆或建筑")
    return (_controlled_order(pointer, UnitAction.PLAYER_ATTACK_TARGET, native_id,
                              house_pointer, basis_frame)
            + pb_uint(3, target) + pb_uint(8, target_native_id)
            + pb_uint(9, target_house) + pb_uint(10, target_type))


def click_event(units, event) -> bytes:
    """`ClickEvent{object_addresses, event}`。

    对象级网络事件走这条通道而非 `UnitOrder`：它不检查 `current_mission`，
    且会检查底层返回值并报错，而 `UnitOrder` 会丢弃返回值导致静默失败。
    """
    out = b"".join(pb_uint(1, _pointer_of(u)) for u in units)
    return out + pb_uint(2, int(event))


def mission_clicked(units, mission, target_object=None,
                    coordinates: Coordinates | None = None) -> bytes:
    """`MissionClicked{object_addresses, event(Mission), target_object, coordinates}`。"""
    out = b"".join(pb_uint(1, _pointer_of(u)) for u in units)
    out += pb_uint(2, int(mission))
    if target_object:
        out += pb_uint(3, _pointer_of(target_object))
    if coordinates is not None:
        out += pb_bytes(4, coordinates_payload(coordinates))
    return out


# ---------------------------------------------------------------- 生产与建造
def object_type_payload(entry: ObjectType) -> bytes:
    """`ObjectTypeClass` 的最小字段集。

    服务端只读取 `pointer_self`（查类型表）、`array_index` 与 `type`（构造
    事件），其余字段传了也会被忽略。
    """
    return (pb_uint(5, entry.array_index) + pb_uint(6, entry.pointer)
            + pb_uint(9, entry.type))


def produce_order(entry: ObjectType) -> bytes:
    """`ProduceOrder{object_type}`。

    服务端从不读取 `action`，三个取值行为相同，故本函数不接受该参数。暂停与
    取消生产请用 `add_event` 的 `SUSPEND` 与 `ABANDON`。
    """
    return pb_bytes(1, object_type_payload(entry))


def place_query(entry: ObjectType, house_pointer, candidates) -> bytes:
    """`PlaceQuery{type_class, house_class, coordinates}`。

    `house_class` 必须给真实 House 指针：proto 注释所称「留空即当前玩家」在
    实现中不存在，传 0 会报 `invalid house 0`。候选坐标是**输入**，函数只返回
    其中合法的子集；超出 `PLACE_QUERY_MAX_LENGTH` 的部分会被服务端静默截断。
    """
    out = pb_uint(1, entry.pointer) + pb_uint(2, _pointer_of(house_pointer))
    for candidate in candidates[:PLACE_QUERY_MAX_LENGTH]:
        out += pb_bytes(3, coordinates_payload(candidate))
    return out


def place_building(building, coordinates: Coordinates) -> bytes:
    """`PlaceBuilding{building, coordinates}`。

    `building` 用 `pointer_self` 定位；服务端据此找到已完工的工厂条目。
    """
    return (pb_bytes(1, pb_uint(10, _pointer_of(building)))
            + pb_bytes(2, coordinates_payload(coordinates)))


# ---------------------------------------------------------------- 引擎事件
#: `StorageValue` 的字段号，用于 `read_value`
STORAGE_GAME_STATE = 1
STORAGE_MAP_DATA = 2
STORAGE_INITIAL_GAME_STATE = 3
STORAGE_EVENT_BUFFER = 4
STORAGE_MAP_DATA_SOA = 5
STORAGE_LOAD_STATE = 6


def read_value(storage_field: int) -> bytes:
    """`ReadValue{data{<field>}}`。

    服务端取 `data` 中第一个被设置的字段并回填，故一次只能读一个。
    """
    return pb_bytes(1, pb_bytes(storage_field, b""))


def add_event(event_type, production=None, cell=None, whom=None,
              frame_delay=0, spoof=False, house_index=0) -> bytes:
    """`AddEvent{event, frame_delay, spoof}`。

    服务端只对五种载荷赋值 `EventClass.Data`：`production`、`place`、
    `sell_cell`、`sell`、`deploy`。其余事件类型会构造出未初始化的 `Data`，
    因此本函数只接受这几种。

    `production` 为 `(rtti_id, heap_id)` 或 `(rtti_id, heap_id, is_naval)`；
    `cell` 为 `Coordinates`；`whom` 为对象指针，用于 `sell` 与 `deploy`。

    `spoof=True` 时事件归属改用 `house_index` 而非当前玩家，帧号也会被取负
    以标记「已伪造」。该行为尚未充分验证。
    """
    from ..constants import NetworkEvent

    event = b""
    if spoof:
        event += pb_uint(2, house_index)
    event += pb_uint(4, int(event_type))

    if production is not None:
        rtti_id, heap_id = production[0], production[1]
        is_naval = production[2] if len(production) > 2 else False
        event += pb_bytes(10, pb_uint(1, rtti_id) + pb_uint(2, heap_id)
                          + pb_uint(3, 1 if is_naval else 0))
    elif cell is not None and event_type == NetworkEvent.SELL_CELL:
        event += pb_bytes(16, pb_bytes(1, coordinates_payload(cell)))
    elif whom is not None and event_type == NetworkEvent.SELL:
        event += pb_bytes(18, pb_bytes(1, _target_class(whom)))
    elif whom is not None and event_type == NetworkEvent.DEPLOY:
        event += pb_bytes(17, pb_bytes(1, _target_class(whom)))

    out = pb_bytes(1, event) + pb_uint(2, frame_delay)
    if spoof:
        out += pb_uint(3, 1)
    return out


def _target_class(pointer) -> bytes:
    """`TargetClass{m_id, m_rtti}`。`m_id` 用对象指针，`m_rtti` 未知时置 0。"""
    return pb_uint(1, _pointer_of(pointer))


# ---------------------------------------------------------------- 其他
def add_message(text, duration_frames=150, color=0) -> bytes:
    """`AddMessage{message, duration_frames, color}`，在游戏内显示一行文本。"""
    return (pb_str(1, text) + pb_uint(2, duration_frames)
            + pb_uint(3, int(color)))


def configuration(parse_map_data_interval=None, single_step=None) -> bytes:
    """`Configuration` 的部分字段。

    只有这两个字段会被 `MainData::update_config` 应用，其余字段发了也不生效。
    `parse_map_data_interval` 为 0 会被 `ConfigData::parse` 强制改回 1。
    """
    out = b""
    if parse_map_data_interval is not None:
        out += pb_uint(4, parse_map_data_interval)
    if single_step is not None:
        out += pb_uint(5, 1 if single_step else 0)
    return out


def inspect_configuration(update=False, **fields) -> bytes:
    """`InspectConfiguration{config, update}`。"""
    return (pb_bytes(1, configuration(**fields))
            + pb_uint(2, 1 if update else 0))


def _pointer_of(obj) -> int:
    """接受对象或裸指针。

    凡带 `pointer` 字段的都算对象：除了 `GameObject`/`ObjectType`，还有 `House`
    （`state.player_house()` 给的就是它，`PlaceQuery` 正需要它的指针）。少认一种
    就会落到 `int(obj)` 上抛 `TypeError`，而调用点多半在「读局势」的路径里——
    实测一次 `int(House)` 能让整个 `status` 不可用。写法与 `identity._pointer_of`
    保持一致。
    """
    if isinstance(obj, (GameObject, ObjectType)):
        return obj.pointer
    pointer = getattr(obj, "pointer", None)
    if pointer is not None:
        return int(pointer)
    return int(obj)
