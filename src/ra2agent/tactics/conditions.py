"""技法的适用条件。

技法在名片里声明条件名，注册表在**调用前**与**筛卡片时**各查一次：前者保证不会
在错误局面里执行，后者保证模型看不到此刻用不上的技法。

条件只读局面与参数，不做判断以外的任何事。新增条件要在这里登记。
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


@condition("cell_explored")
def cell_explored(context) -> bool:
    """参数里的目标格已探索。只用于确实需要已知地形的技法。"""
    cell = context.params.get("cell")
    map_data = context.observation.map_data
    if map_data is None or not isinstance(cell, (tuple, list)) or len(cell) != 2:
        return False
    return map_data.in_bounds(cell[0], cell[1]) and not map_data.shrouded(*cell)
