"""技法的适用条件。

技法在名片里声明条件名，注册表在**调用前**与**筛卡片时**各查一次：前者保证不会
在错误局面里执行，后者保证模型看不到此刻用不上的技法。

条件只读局面与参数，不做判断以外的任何事。新增条件要在这里登记。

## 写条件时的两条契约

**一、`subject` 有两种，同一份 `requires` 要同时适配。** 受理 `call` 时是
`command.UnitPool`（含待放置对象，有 `pending()`）；技法真跑起来时是 `micro.Squad`
（只有这条任务名下的单位，没有 `pending()`）。**能用 `context.observation` 判的
就别碰 `subject`**——碰了就要两路都写对，而只认 `UnitPool` 的写法会让技法受理通过、
运行时却永远调不动。需要单位名单时用 `subject.agents()`，它两边都有。

**二、参数可能缺。** 受理点在 `check_params` 之前就判条件（为了不改变拒因次序），
故探针里的 `params` 是**原始请求**，默认值尚未补上：条件要按 `.get()` 取并自行容忍
缺项。

**三、读参数的条件要申报 `needs_params=True`。** 卡片筛选（`tactics` 工具）不带参数，
注册表据此**跳过**这类条件，而不是把它判否——判否会把 `build_structure`、`train_unit`
这类 `requires=("can_afford",)` 的技法永久藏起来，模型只能读源码才知道它们存在。
"""
from ..errors import TacticError
from ..runtime.formation import IMPASSABLE

#: 条件名到判据。
CONDITIONS: dict = {}

#: 需要调用参数才判得出来的条件名。卡片筛选没有参数，故跳过它们。
NEEDS_PARAMS: set = set()


def condition(name, *, needs_params=False):
    """把判据登记为条件。

    `needs_params=True` 用于读 `context.params` 的条件：没有参数时它判不出真假，
    只能跳过（见模块开头契约三）。
    """
    def decorate(function):
        CONDITIONS[name] = function
        if needs_params:
            NEEDS_PARAMS.add(name)
        return function
    return decorate


def check_conditions(names, context) -> tuple:
    """返回不满足的条件名。未登记的条件名报错，不静默放行。"""
    missing = []
    for name in names:
        check = CONDITIONS.get(name)
        if check is None:
            raise TacticError(f"未登记的适用条件：{name!r}")
        if not check(context):
            missing.append(name)
    return tuple(missing)


#: 条件名 → 给模型看的人话。只写「光看名字等于没说」的那几条：拒因要能指导下一步，
#: 否则模型只知道「此刻用不上」，不知道该补什么。
HINTS = {
    "stop_v1": "DLL 未声明 Stop 接口 v1；不能使用玩家停止输入",
    "guard_v1": "DLL 未声明 Guard 接口 v1；不能使用原生警戒输入",
    "prereq_met": "建造前提没满足，或这个类型不在可造清单里（见 status 的「可造」段）",
    "cell_passable": "目标格不可通行或在地图外（水、岩石、墙）",
    "can_afford": "钱不够",
    "type_not_pending": "这一型已经在生产队列或已完工待放置了"
                        "——先把它放下/等它出来，别重复下同一单",
}


def explain(names) -> str:
    """把不满足的条件名渲染成人话；没写提示的保留原名。"""
    return "、".join(f"{name}（{HINTS[name]}）" if name in HINTS else name
                     for name in names)


@condition("has_units")
def has_units(context) -> bool:
    """这一队至少有一个可用单位。"""
    return bool(context.subject.agents())


@condition("has_map")
def has_map(context) -> bool:
    """已有底图，坐标类技法才谈得上。"""
    return context.observation.map_data is not None


@condition("stop_v1")
def stop_v1(context) -> bool:
    state = context.observation.state
    return state is not None and state.stop_interface_version == 1


@condition("guard_v1")
def guard_v1(context) -> bool:
    """仅使用已声明且认识的接口版本，不通过下令探测能力。"""
    state = context.observation.state
    return state is not None and state.guard_interface_version == 1


@condition("has_enemies")
def has_enemies(context) -> bool:
    """当前看得到敌人。"""
    return bool(context.observation.visible_enemies)


@condition("no_enemies")
def no_enemies(context) -> bool:
    """当前看不到敌人。"""
    return not context.observation.visible_enemies


@condition("has_pending_building")
def has_pending_building(context) -> bool:
    """手上有完工待放置的建筑（停在 limbo 里那栋）。

    只看局面，不碰 `subject`：`subject` 有两种形态（受理时 `UnitPool` 有 `pending()`、
    运行时 `Squad` 没有），只认前者的写法会让技法受理通过、运行时却永远调不动。
    """
    state = context.observation.state
    if state is None:
        return False
    return any(obj.in_limbo for obj in state.own_objects())


@condition("cell_explored", needs_params=True)
def cell_explored(context) -> bool:
    """参数里的目标格已探索。只用于确实需要已知地形的技法。"""
    cell = context.params.get("cell")
    map_data = context.observation.map_data
    if map_data is None or not isinstance(cell, (tuple, list)) or len(cell) != 2:
        return False
    return map_data.in_bounds(cell[0], cell[1]) and not map_data.shrouded(*cell)


@condition("cell_unknown", needs_params=True)
def cell_unknown(context) -> bool:
    """参数里的目标格**还没**探索过。侦察技法用它，不必自己取反。

    参数相关的条件依赖注册表把调用参数带进探针（`missing_conditions` 已支持）。
    卡片筛选拿不到参数，故注册表对这类条件（`needs_params`）**跳过**，只在 `call`
    受理与技法真跑时生效——这样卡片不会提前消失，受理时的拒绝又是诚实的。
    """
    return not cell_explored(context)


def _player_house(context):
    """本进程控制的阵营；拿不到或不止一个时给 `None`（不抛，条件里只判真假）。"""
    state = context.observation.state
    if state is None:
        return None
    mine = [house for house in state.houses if house.current_player]
    return mine[0] if len(mine) == 1 else None


def _param_type(context):
    """参数里点名的类型。`type` 与 `name` 都认，方便不同措辞的技法共用。"""
    for key in ("type", "name"):
        value = context.params.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _catalogue(context):
    """本次观测带下来的可造目录；没有则 `None`（缺它只是少了前提判断）。"""
    return getattr(context.observation, "catalogue", None)


def _catalogue_entry(context):
    """参数点名的类型在目录里的条目。"""
    catalogue = _catalogue(context)
    name = _param_type(context)
    if catalogue is None or name is None:
        return None
    return catalogue.entry(name)


def _owned_building_ids(context):
    """己方已在地图上的建筑注册名——实现共用 `catalogue.owned_building_ids`。"""
    from ..data.catalogue import owned_building_ids
    return owned_building_ids(context.observation.state, context.types,
                              _catalogue(context))


@condition("can_afford", needs_params=True)
def can_afford(context) -> bool:
    """参数点名的类型买得起。

    价格只从类型表取；类型解析不出、或拿不到钱数时**判否**——宁可不让这条技法
    跑，也不要先下单再让引擎因钱不够拒绝。

    `needs_params=True`：卡片筛选拿不到参数，注册表据此跳过它，故这条条件不会让
    卡片消失，只在 `call` 受理与技法真跑时生效。
    """
    name = _param_type(context)
    types = context.types
    if name is None or types is None:
        return False
    entry = types.resolve(name)
    house = _player_house(context)
    if entry is None or house is None:
        return False
    return house.money >= entry.cost


@condition("has_construction_yard")
def has_construction_yard(context) -> bool:
    """己方有一栋建造厂。

    按类型显示名认（引擎给的是 `Allied/Soviet/Yuri Construction Yard`），免得
    依赖注册名别名有没有挂上。
    """
    state = context.observation.state
    types = context.types
    if state is None or types is None:
        return False
    for obj in state.own_objects():
        if obj.in_limbo:
            continue
        entry = types.info(obj)
        if entry is not None and "construction yard" in (entry.name or "").lower():
            return True
    return False


@condition("prereq_met", needs_params=True)
def prereq_met(context) -> bool:
    """参数点名的类型，**建造前提是否已经满足**。

    引擎只在真下单之后才回一句 `unbuildable object_type {…}`——既不说是缺前提还是
    缺钱，也不说缺哪个。这条条件把那份判断提前到受理点：满足不了就当场拒绝，模型
    不必用一次 call 与几拍去换拒绝原因。

    目录来自 `corpus/derived/rules.json`（`ra2agent.data.catalogue`），随观测下发。**读不到
    目录时判真**（放行）：缺一份数据不该让模型连电厂都造不出来——那种情况下退回
    原来的行为（真下单、让引擎拒），比全面禁建安全得多。目录在手而类型不在清单里
    才是判否，那说明它本来就不是能造的东西。
    """
    catalogue = _catalogue(context)
    if catalogue is None:
        return True
    entry = _catalogue_entry(context)
    if entry is None or not entry.buildable:
        return False
    from ..data.catalogue import own_building_cells, stolen_labels, water_nearby
    observation = context.observation
    # 两条引擎的额外门也要算：要偷到的科技、临水建筑有没有水面。少算它们，模型
    # 就会拿到「本地说能造、引擎说 unbuildable」的假 ✓（实测超时空突击队与船厂）。
    return not entry.missing(
        _owned_building_ids(context),
        stolen=stolen_labels(observation.house),
        water_near=water_nearby(observation.map_data,
                                own_building_cells(observation.state)))


@condition("cell_passable", needs_params=True)
def cell_passable(context) -> bool:
    """参数里的目标格站得住人：在图内，且地形不是水 / 岩石 / 墙。

    `invalid cell` 是引擎对这类格的回话，但只在真下令之后才说；把它提到受理点，
    模型就不必靠一次次被拒去试出哪格能走（实测两个测试员都为这个白烧过 call）。

    **不判「已探索」**：往未探索处推进是正常玩法，无权拦。
    """
    cell = context.params.get("cell")
    map_data = context.observation.map_data
    if map_data is None or not isinstance(cell, (tuple, list)) or len(cell) != 2:
        return False
    x, y = cell
    if not map_data.in_bounds(x, y):
        return False
    return map_data.land_type(x, y) not in IMPASSABLE


@condition("has_factory")
def has_factory(context) -> bool:
    """己方有生产队列条目（即有生产建筑）。

    未实测「工厂空闲时引擎是否也列条目」，故不要拿它当唯一门槛。
    """
    state = context.observation.state
    return bool(state is not None and state.own_factories())


@condition("type_not_pending", needs_params=True)
def type_not_pending(context) -> bool:
    """参数点名的类型**不在**生产队列里、也不在待放置里。

    原版对建筑不允许同型重复排队：第二次同型下单会被引擎**悄悄吞掉**——任务既不
    结算也没有产出（实测「第二座矿厂走到 37/54 后无声消失、也没有 failed 结果」）。
    把它拦在受理点，模型当场知道该先放下或等它出来，而不是白等一场。

    解析不出类型名时判真：名字本身有问题该由 `can_afford` / `prereq_met` 去报，
    不在这里叠一条。
    """
    name = _param_type(context)
    want = context.type_pointer(name) if name else None
    if want is None:
        return True
    return want not in _pending_type_pointers(context)


def _pending_type_pointers(context):
    """正在生产或已完工待放置的对象类型指针。"""
    state = context.observation.state
    types = context.types
    if state is None or types is None:
        return frozenset()
    out = set()
    for factory in state.own_factories():
        pointers = list(factory.queued_objects)
        if factory.completed:
            # 建筑厂完工时产出物就是 `factory.object`；单位厂这里加的是厂自己，
            # 与「请求的类型」不会撞上，无害。
            pointers.append(factory.object)
        for pointer in pointers:
            obj = state.object(pointer)
            entry = types.info(obj) if obj is not None else None
            if entry is not None:
                out.add(entry.pointer)
    return frozenset(out)
