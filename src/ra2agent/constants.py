"""协议常量与枚举，取自 `proto/ra2yrproto/` 的定义。

枚举值均与 proto 一致；只列本项目实际使用的部分。
"""
from enum import IntEnum

# ---------------------------------------------------------------- 传输
CMD_NONE, CMD_SHUTDOWN, CMD_CLIENT = 0, 1, 2
CMD_CLIENT_OLD, CMD_POLL, CMD_POLL_BLOCKING = 3, 4, 5

#: 命令与结果的 protobuf 包名
NS = "ra2yrproto.commands."
#: 核心消息的 protobuf 包名
NS_CORE = "ra2yrproto."

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 14521

#: 一格的世界坐标长度。见 YRpp `CellClass::Cell2Coord`
LEPTONS_PER_CELL = 256
#: `Factory.progress_timer` 到该值即完工
PRODUCTION_STEPS = 54
#: `PlaceQuery` 一次能接受的候选坐标上限，超出静默截断
PLACE_QUERY_MAX_LENGTH = 1024
#: 建筑放置的候选落点相对中心向外的搜索半径（格）
PLACE_SITE_RADIUS = 10
#: 一条任务「等局面变化」最多等多少帧。等满就收工交还单位，不许永久占着。
#: 建一栋楼约 540-950 帧，故留约两个周期；技法可用 `wait_grace_frames=None` 豁免。
WAIT_GRACE_FRAMES = 2400


class UnitAction(IntEnum):
    """`UnitOrder.action`。"""

    NONE = 0
    DEPLOY = 1
    SELECT = 2
    UNSELECT = 3
    TRY_TO_DEPLOY = 4
    SELL = 5
    MOVE = 6
    CAPTURE = 7
    ATTACK = 8
    REPAIR = 9
    STOP = 10
    SELL_CELL = 11
    ATTACK_MOVE = 12
    # Local DLL extension v1; deliberately excluded from the old action whitelist.
    GUARD_CURRENT = 13
    GUARD_POSITION = 14
    PLAYER_STOP = 15
    PLAYER_ATTACK_TARGET = 16


#: 服务端 `UnitOrder` 的 switch 实际实现的动作。
#: 其余值落入 default 分支抛 `invalid unit action`，见命令接口源码结论。
UNIT_ACTIONS_IMPLEMENTED = frozenset({
    UnitAction.DEPLOY, UnitAction.SELECT, UnitAction.SELL, UnitAction.SELL_CELL,
    UnitAction.MOVE, UnitAction.CAPTURE, UnitAction.ATTACK,
    UnitAction.ATTACK_MOVE, UnitAction.STOP, UnitAction.REPAIR,
})

#: 需要 `target_object` 的动作。
UNIT_ACTIONS_NEED_TARGET = frozenset({
    UnitAction.CAPTURE, UnitAction.ATTACK, UnitAction.REPAIR,
})

#: 需要 `coordinates` 的动作。
UNIT_ACTIONS_NEED_CELL = frozenset({UnitAction.MOVE, UnitAction.ATTACK_MOVE})


class Mission(IntEnum):
    """`Object.current_mission`。"""

    SLEEP = 0
    ATTACK = 1
    MOVE = 2
    QMOVE = 3
    RETREAT = 4
    GUARD = 5
    STICKY = 6
    ENTER = 7
    CAPTURE = 8
    EATEN = 9
    HARVEST = 10
    AREA_GUARD = 11
    RETURN = 12
    STOP = 13
    AMBUSH = 14
    HUNT = 15
    UNLOAD = 16
    SABOTAGE = 17
    CONSTRUCTION = 18
    SELLING = 19
    REPAIR = 20
    RESCUE = 21
    MISSILE = 22
    HARMLESS = 23
    OPEN = 24
    PATROL = 25
    PARADROP_APPROACH = 26
    PARADROP_OVERFLY = 27
    WAIT = 28
    ATTACK_MOVE = 29
    SPYPLANE_APPROACH = 30
    SPYPLANE_OVERFLY = 31


#: proto 中 `Mission_None` 为 -1，在 `Object.current_mission` 上同样如此。
MISSION_NONE = -1

#: `UnitOrder` 会拒绝处于这些任务的对象，见 `commands_game.cpp::is_illegal_mission`。
MISSIONS_ILLEGAL_FOR_UNIT_ORDER = frozenset({MISSION_NONE, Mission.CONSTRUCTION})


class AbstractType(IntEnum):
    """`Object.object_type` 与 `ObjectTypeClass.type`。"""

    NONE = 0
    UNIT = 1
    AIRCRAFT = 2
    BUILDING = 6
    BUILDINGTYPE = 7
    INFANTRY = 15
    UNITTYPE = 40


class ProduceAction(IntEnum):
    """`ProduceOrder.action`。

    **服务端从不读取该字段**，三个取值行为相同：投递一次生产事件。暂停与
    取消生产须改用 `AddEvent` 的 `SUSPEND` 与 `ABANDON`。
    """

    NONE = 0
    BEGIN = 1
    HOLD = 2
    CANCEL = 3


class NetworkEvent(IntEnum):
    """`Event.event_type`。只列本项目使用的部分。"""

    POWER_ON = 0x1
    POWER_OFF = 0x2
    IDLE = 0x6
    SCATTER = 0x7
    DESTRUCT = 0x8
    DEPLOY = 0x9
    DETONATE = 0xA
    PLACE = 0xB
    PRODUCE = 0xE
    SUSPEND = 0xF
    ABANDON = 0x10
    SPECIAL_PLACE = 0x12
    REPAIR = 0x15
    SELL = 0x16
    SELL_CELL = 0x17
    SPECIAL = 0x18


class LoadStage(IntEnum):
    """`GameState.stage`。"""

    NONE = 0
    LOADING = 1
    INGAME = 2
    EXIT_GAME = 3


class LandType(IntEnum):
    """`Cell.land_type`。"""

    CLEAR = 0
    ROAD = 1
    WATER = 2
    ROCK = 3
    WALL = 4
    TIBERIUM = 5
    BEACH = 6
    ROUGH = 7
    ICE = 8
    RAILROAD = 9
    TUNNEL = 10
    WEEDS = 11
