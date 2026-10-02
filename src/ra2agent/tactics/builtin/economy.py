"""经济与电力类技法：矿车与供电。

玩家把这两样合称「发展」，而它们的共同点是**眼睛一闭也该发生**：

- 停工矿车需要恢复采矿。Guard v1 的 CMIN 使用一次原版 G 输入；旧 DLL 与其他
  矿车型号保留移回已探索矿格的兼容路径。两者都不以输入回执承诺采矿效果。
- 电力入不敷出会让生产变慢，而补一座电厂是无判断余地的动作。

故主路径做成自动脉冲：不占单位租约、空转不报给模型，模型只在被唤醒时做取舍。
"""
from ...constants import MISSION_NONE, Mission
from ...runtime.intents import GuardCurrent, MoveTo, Stance
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

#: 同一台矿车重复相同恢复输入的最短间隔，免得每拍重发打断原生 AI。
REPEAT_EVERY_FRAMES = 600

#: 矿车处于这些任务时视为「停工」：没在采矿，也没在往返的路上。
#: 正在采矿（`HARVEST`）与正在往返（`MOVE`/`RETURN`/`ENTER`/`UNLOAD`）的不去打扰——
#: AREA_GUARD 已交给原生 AI，不能仅因尚未进入 HARVEST 就判成停工。
IDLE_MISSIONS = (Mission.STOP, Mission.GUARD, Mission.SLEEP, MISSION_NONE)

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
    """恢复点名矿车：已验证的 CMIN 优先原生 G，否则使用矿格移动。"""
    out = []
    for agent, obj in _subject_harvesters(context):
        intent = _harvest_intent(context, agent, obj)
        if intent is not None:
            out.append(intent)
    return tuple(out)


def _harvest_intent(context, agent, obj):
    """不把未实测型号或未知接口版本当成已验证的原生采矿能力。"""
    state = context.observation.state
    entry = _entry_of(context, obj)
    if (state is not None and state.guard_interface_version == 1
            and entry is not None and entry.id == "CMIN"):
        # 缺失身份等错误仍交给 L0 拒绝，不能用旧移动掩盖 v1 数据异常。
        return context.intent(GuardCurrent, units=(agent,))
    cell = nearest_ore(context.observation.map_data, obj.coordinates.cell)
    if cell is None:
        return None
    return context.intent(MoveTo, units=(agent,), cell=cell, stance=Stance.PASSIVE)


def _auto_harvest(context):
    """恢复停工矿车；相同原生 G 或矿格移动使用跨拍冷却，不打断原生 AI。"""
    map_data = context.observation.map_data
    state = context.observation.state
    if map_data is None or state is None:
        return ()
    frame = context.frame
    # Agent ID 隔离同指针的新对象，避免旧矿车的冷却污染复用地址后的新单位。
    harvesters = _own_harvesters(context)
    # CMIN 回矿厂时可短暂 limbo；仍存在的己方身份保留冷却。
    available = {context.subject.agent_id(obj.pointer)
                 for obj in state.own_objects()}
    seen = {agent: value for agent, value in (context.recall("recent") or {}).items()
            if agent in available}
    allowed = set(context.subject.agents())
    out = []
    for pointer, obj in harvesters:
        if obj.mission not in IDLE_MISSIONS:
            continue
        agent = context.subject.agent_id(pointer)
        if agent is None or agent not in allowed:
            continue
        intent = _harvest_intent(context, agent, obj)
        if intent is None:
            continue
        operation = (intent.kind, getattr(intent, "cell", None))
        when, previous = seen.get(agent, (None, None))
        if (when is not None and 0 <= frame - when < REPEAT_EVERY_FRAMES
                and previous == operation):
            continue
        seen[agent] = (frame, operation)
        out.append(intent)
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
        summary="恢复点名矿车采矿：Guard v1 的 CMIN 提交一次 G，其他情况移向已探索矿格；"
                "回执不保证已开始采矿，结算释放租约后原生 AI 继续运行",
        version=2,
        requires=("has_units", "has_map"),
        idle_ends_task=True,
    ), _harvest),

    Tactic(TacticInfo(
        name="auto_harvest",
        summary="停工矿车自动恢复：v1 CMIN 使用一次 G，其他情况移向矿格；不打断采矿、往返或地点警戒",
        version=2,
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
