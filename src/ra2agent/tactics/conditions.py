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
缺项。卡片筛选时更是完全没有参数，故参数型条件不会让卡片消失，只影响 `call` 受理
与技法真跑。
"""
from ..errors import TacticError

#: 条件名到判据。
CONDITIONS: dict = {}


def condition(name):
    """把判据登记为条件。"""
    def decorate(function):
        CONDITIONS[name] = function
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


@condition("has_units")
def has_units(context) -> bool:
    """这一队至少有一个可用单位。"""
    return bool(context.subject.agents())


@condition("has_map")
def has_map(context) -> bool:
    """已有底图，坐标类技法才谈得上。"""
    return context.observation.map_data is not None


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


@condition("cell_explored")
def cell_explored(context) -> bool:
    """参数里的目标格已探索。只用于确实需要已知地形的技法。"""
    cell = context.params.get("cell")
    map_data = context.observation.map_data
    if map_data is None or not isinstance(cell, (tuple, list)) or len(cell) != 2:
        return False
    return map_data.in_bounds(cell[0], cell[1]) and not map_data.shrouded(*cell)


@condition("cell_unknown")
def cell_unknown(context) -> bool:
    """参数里的目标格**还没**探索过。侦察技法用它，不必自己取反。

    参数相关的条件依赖注册表把调用参数带进探针（`missing_conditions` 已支持）。
    **但卡片筛选拿不到参数**（`tactics` 工具不带参数），故参数型条件只在 `call`
    受理与技法真跑时生效，不会让卡片提前消失。
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


@condition("can_afford")
def can_afford(context) -> bool:
    """参数点名的类型买得起。

    价格只从类型表取；类型解析不出、或拿不到钱数时**判否**——宁可不让这条技法
    跑，也不要先下单再让引擎因钱不够拒绝。

    与 `cell_unknown` 同理：**卡片筛选拿不到参数**，故它只能让 `call` 被拒得有理有据，
    不会让卡片提前消失。
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


@condition("has_factory")
def has_factory(context) -> bool:
    """己方有生产队列条目（即有生产建筑）。

    未实测「工厂空闲时引擎是否也列条目」，故不要拿它当唯一门槛。
    """
    state = context.observation.state
    return bool(state is not None and state.own_factories())
