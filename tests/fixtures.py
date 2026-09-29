"""测试用的消息构造器。

用 `proto` 的编码器手工拼装，使测试不依赖录制文件、可完全离线运行。
"""
from ra2agent.constants import AbstractType, LandType, Mission
from ra2agent.proto import pb_bytes, pb_str, pb_uint

PLAYER_HOUSE = 0x1000
ENEMY_HOUSE = 0x2000
NEUTRAL_HOUSE = 0x3000


def build_coordinates(x, y, z=0):
    """`Coordinates`。"""
    return pb_uint(1, x) + pb_uint(2, y) + pb_uint(3, z)


def build_object(pointer, type_pointer=0x900, house=PLAYER_HOUSE,
                 object_type=AbstractType.UNIT, mission=Mission.GUARD,
                 x=1000, y=2000, health=300, in_limbo=False, deployed=False,
                 selected=False, on_map=True, destination=None):
    """`Object`。`destination` 为 `(x, y)`；不给时服务端字段缺席。"""
    return (
        pb_uint(1, type_pointer)
        + pb_uint(2, health)
        + pb_bytes(3, build_coordinates(x, y))
        + pb_uint(4, house)
        + pb_uint(9, int(object_type))
        + pb_uint(10, pointer)
        + pb_uint(13, 1 if selected else 0)
        + pb_uint(14, 1 if deployed else 0)
        + (pb_bytes(17, build_coordinates(*destination))
           if destination is not None else b"")
        + pb_uint(18, int(mission))
        + pb_uint(19, 1 if in_limbo else 0)
        + pb_uint(20, 1 if on_map else 0)
    )


def build_house(pointer, current_player=False, faction="Alliance",
                money=10000, defeated=False):
    """`House`。"""
    return (
        pb_uint(1, 0)
        + pb_str(2, "me" if current_player else "other")
        + pb_str(3, faction)
        + pb_uint(4, 1 if defeated else 0)
        + pb_uint(5, 1 if current_player else 0)
        + pb_uint(7, money)
        + pb_uint(8, pointer)
    )


def build_factory(owner, obj, timer=0, queued=(), on_hold=False,
                  production_steps=54):
    """`Factory`。"""
    out = pb_uint(1, timer) + pb_uint(2, owner) + pb_uint(3, obj)
    for item in queued:
        out += pb_uint(4, item)
    out += pb_uint(5, 1 if on_hold else 0)
    out += pb_uint(6, 1 if timer >= production_steps else 0)
    return out


def build_cell(index, land_type=LandType.CLEAR, shrouded=False):
    """`Cell`。"""
    return (pb_uint(1, int(land_type)) + pb_uint(9, 1 if shrouded else 0)
            + pb_uint(13, index))


def build_game_state(objects=(), houses=(), factories=(), cells=(),
                     frame=1234):
    """`GameState`。"""
    out = pb_uint(1, frame) + pb_uint(7, 2) + pb_uint(14, 10)
    for factory in factories:
        out += pb_bytes(3, factory)
    for house in houses:
        out += pb_bytes(4, house)
    for obj in objects:
        out += pb_bytes(6, obj)
    for cell in cells:
        out += pb_bytes(15, cell)
    return out


def build_map_soa(width, height, shrouded, land, passability=None):
    """`ReadValue{data{map_data_soa}}` 的响应，即一张地图。"""
    if passability is None:
        passability = [1] * (width * height)
    soa = (
        pb_bytes(1, bytes(land))
        + pb_bytes(7, bytes(shrouded))
        + pb_bytes(8, b"".join(bytes([v]) for v in passability))
        + pb_uint(9, width) + pb_uint(10, height)
    )
    return pb_bytes(1, pb_bytes(5, soa))


def build_type_table(entries):
    """`ReadValue{data{initial_game_state}}` 的响应，即类型表。

    `entries` 为 `(name, cost, array_index, pointer, rtti)` 序列。
    """
    out = b""
    for name, cost, array_index, pointer, rtti in entries:
        out += pb_bytes(5, pb_str(1, name) + pb_uint(2, cost)
                        + pb_uint(5, array_index) + pb_uint(6, pointer)
                        + pb_uint(9, int(rtti)))
    return pb_bytes(1, pb_bytes(3, out))
