"""经济与电力类技法：矿车与供电。

玩家把这两样合称「发展」，而它们的共同点是**眼睛一闭也该发生**：

- 矿车被 `STOP` 过就不会自己恢复采矿——引擎没有采矿动作（`Mission.HARVEST` 只能从
  观测里读到、下不去），唯一的路是把它**移回矿格**让游戏自身的采矿 AI 接管。实测
  一局因矿车停工、资金长期停在 100，什么也造不出来。
- 电力入不敷出会让生产变慢，而补一座电厂是无判断余地的动作。

故主路径做成自动脉冲：不占单位租约、空转不报给模型，模型只在被唤醒时做取舍。
"""
from ...constants import MISSION_NONE, Mission
from ...runtime.intents import MoveTo, Stance
from ...data.catalogue import pending_building_ids
from ..core import (Param, Tactic, TacticInfo, Trigger, is_positive_int)

#: 供电建筑的候选注册名（与 `data/catalogue.py` 的 `ALIASES` 同源），按顺序试：
#: 不是我们这一方的会被前提门拒掉，试到能过的那个就是我们的。
POWER_PLANTS = ("GAPOWR", "NAPOWR", "YAPOWR")

#: 矿车的候选注册名。`SMON`（`ZZZ Useless`）是规则文件里的废弃条目，不收。
HARVESTERS = ("CMIN", "CMON", "HARV", "HORV")

#: 多久看一次矿车、多久看一次电力。都比 `deploy_mcv` 慢——经济是分钟级的事。
HARVEST_EVERY_FRAMES = 60
POWER_EVERY_FRAMES = 120

#: 找矿时从矿车往外搜多远（格）。更远的矿不如让模型自己决定去哪一片。
ORE_SEARCH_RADIUS = 40

#: 同一台矿车派往同一片矿的最短间隔，免得每拍重发同一条移动令。
REPEAT_EVERY_FRAMES = 600

#: 矿车处于这些任务时视为「停工」：没在采矿，也没在往返的路上。
#: 正在采矿（`HARVEST`）与正在往返（`MOVE`/`RETURN`/`ENTER`/`UNLOAD`）的不去打扰——
#: 每拍重发移动令会让它永远在路上。
IDLE_MISSIONS = (Mission.STOP, Mission.GUARD, Mission.SLEEP,
                 Mission.AREA_GUARD, MISSION_NONE)

#: 默认想维持的矿车数量。
DEFAULT_HARVESTER_TARGET = 4


def _entry_of(context, obj):
    """这个对象的目录条目；类型表或目录还没到时给 `None`。"""
    catalogue = context.observation.catalogue
    types = context.observation.types
    if catalogue is None or types is None:
        return None
    return catalogue.by_name.get(types.name(obj, ""))


def _own_harvesters(context):
    """己方**在地图上**的矿车 `[(指针, 对象)]`。

    从 `state` 数而不是从主体数：模型点名「哪几台矿车」只决定**动谁**，而「我们一共
    有几台」得看全局，否则模型只点一台时数量判断会失真。
    """
    state = context.observation.state
    if state is None:
        return []
    out = []
    for obj in state.own_objects():
        if obj.in_limbo:
            continue
        entry = _entry_of(context, obj)
        if entry is not None and entry.harvester:
            out.append((obj.pointer, obj))
    return out


def _subject_harvesters(context):
    """主体里那些矿车 `[(agent_id, 对象)]`。

    模型点名了谁就只动谁；自动脉冲的主体是全部己方单位，故它等价于全部矿车——
    `auto_harvest` 自己改用 `_own_harvesters` 直接看全局，不走这里。
    """
    out = []
    for agent in context.subject.agents():
        obj = context.subject.object_of(agent)
        if obj is None or obj.in_limbo:
            continue
        entry = _entry_of(context, obj)
        if entry is not None and entry.harvester:
            out.append((agent, obj))
    return out


def nearest_ore(map_data, cell, *, radius=ORE_SEARCH_RADIUS):
    """离 `cell` 最近的**已探索**矿格；半径内没有给 `None`。

    逐圈由近及远：先看近处，某圈一旦有矿就停——更远那片要走更久。未探索的格不算：
    看不见的地方不该下令过去。
    """
    if map_data is None:
        return None
    for step in range(0, radius + 1):
        best = None
        for x, y in _ring(cell, step):
            if not map_data.in_bounds(x, y) or not map_data.is_explored(x, y):
                continue
            if not map_data.tiberium_value(x, y):
                continue
            span = max(abs(x - cell[0]), abs(y - cell[1]))
            if best is None or (span, x, y) < best[0]:
                best = ((span, x, y), (x, y))
        if best is not None:
            return best[1]
    return None


def _ring(cell, step):
    """以 `cell` 为中心、切比雪夫距离恰为 `step` 的一圈格。"""
    if step == 0:
        return (cell,)
    x0, y0 = cell
    out = []
    for dx in range(-step, step + 1):
        out.append((x0 + dx, y0 - step))
        out.append((x0 + dx, y0 + step))
    for dy in range(-step + 1, step):
        out.append((x0 - step, y0 + dy))
        out.append((x0 + step, y0 + dy))
    return tuple(out)


def _harvest(context):
    """把点名的矿车移到最近的矿格。

    模块没有采矿动作，故「采矿」= 移到矿上，剩下的交给游戏自身的 AI。
    """
    map_data = context.observation.map_data
    out = []
    for agent, obj in _subject_harvesters(context):
        cell = nearest_ore(map_data, obj.coordinates.cell)
        if cell is None:
            continue
        out.append(context.intent(MoveTo, units=(agent,), cell=cell,
                                  stance=Stance.PASSIVE))
    return tuple(out)


def _auto_harvest(context):
    """停工的矿车自动派回最近的矿格。

    只碰停工的：详情见 `IDLE_MISSIONS` 的注释。同一台车派往同一片矿有最短间隔，
    免得它到了却没恢复采矿时每拍重发同一条移动令（那会把它钉在原地）。
    """
    map_data = context.observation.map_data
    if map_data is None:
        return ()
    frame = context.frame
    seen = dict(context.recall("recent") or {})
    out = []
    for pointer, obj in _own_harvesters(context):
        if obj.mission not in IDLE_MISSIONS:
            continue
        cell = nearest_ore(map_data, obj.coordinates.cell)
        if cell is None:
            continue
        when, cell_was = seen.get(pointer, (None, None))
        if when is not None and frame - when < REPEAT_EVERY_FRAMES and cell_was == cell:
            continue
        agent = context.subject.agent_id(pointer)
        if agent is None:
            continue
        seen[pointer] = (frame, cell)
        out.append(context.intent(MoveTo, units=(agent,), cell=cell,
                                  stance=Stance.PASSIVE))
    if out:
        context.remember("recent", seen)
    return tuple(out)


def _line_busy(context) -> bool:
    """生产线上已经有活在排（任一工厂队列非空）。

    载具生产是**全局单线**（实测：多座兵工厂只是冗余），故自动补矿车会和模型排的
    坦克抢那一条线——实测一个玩家抱怨「自动层在偷生产线，这一台等于少出一台半灰熊，
    而且我撤不掉它」。自动层不该抢模型的产能。
    """
    state = context.observation.state
    if state is None:
        return False
    return any(tuple(factory.queued_objects) for factory in state.own_factories())


def _keep_harvesters(context):
    """矿车不够目标数就补一台；够了、或生产线正忙就不造。"""
    target = int(context.params["target"])
    if len(_own_harvesters(context)) >= target or _line_busy(context):
        return ()
    for name in HARVESTERS:
        intents = context.call("train_unit", optional=True, type=name)
        if intents:
            return intents
    return ()


def _keep_power(context):
    """电力入不敷出就补一座电厂。

    只在**真的**入不敷出时动手（`power_drain > power_output`），不做「提前多造」——
    电厂的选址与数量是发展策略，交给模型判断。
    """
    house = context.observation.house
    if house is None or not house.is_low_power:
        return ()
    catalogue = context.observation.catalogue
    state = context.observation.state
    types = context.observation.types
    if catalogue is None or state is None or types is None:
        return ()
    if pending_building_ids(state, types, catalogue):
        return ()                      # 建造厂正忙，等它
    for name in POWER_PLANTS:
        intents = context.call("build_structure", optional=True, type=name)
        if intents:
            return intents
    return ()


TACTICS = (
    Tactic(TacticInfo(
        name="harvest",
        summary="把点名的矿车移到最近的矿石格；采矿交给游戏自己的 AI",
        requires=("has_units", "has_map"),
        idle_ends_task=True,
    ), _harvest),

    Tactic(TacticInfo(
        name="auto_harvest",
        summary="自己跑：把停工（没在采矿也没在往返）的矿车派回最近的矿格",
        trigger=Trigger.every(HARVEST_EVERY_FRAMES),
        idle_ends_task=True,
    ), _auto_harvest),

    Tactic(TacticInfo(
        name="keep_harvesters",
        summary="自己跑：矿车少于目标数就补一台",
        params=(Param("target", DEFAULT_HARVESTER_TARGET,
                      "想维持的矿车数量", is_positive_int),),
        trigger=Trigger.every(POWER_EVERY_FRAMES),
        idle_ends_task=True,
    ), _keep_harvesters),

    Tactic(TacticInfo(
        name="keep_power",
        summary="自己跑：电力入不敷出时补一座电厂",
        trigger=Trigger.every(POWER_EVERY_FRAMES),
        idle_ends_task=True,
    ), _keep_power),
)
