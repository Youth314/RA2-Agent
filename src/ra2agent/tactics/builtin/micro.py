"""内置技法：首批示范。

五条暴露给模型，一条只供组合调用。它们只做「按当前局面产出意图」这一件事：
不记状态、不判失败、不重试——那些是运行时的活，见 `ra2agent/micro.py`。
"""
from ...formation import blocked_cells, formation_cells
from ...intents import Attack, Hold, MoveTo, Stance
from ..core import (REQUIRED, Param, Tactic, TacticInfo, is_cell,
                    is_non_negative_int, is_positive_number, is_stance)


def _hold(context):
    """原地驻守：一条命令带全部对象，实测多对象同令可用。"""
    units = context.subject.agents()
    return (context.intent(Hold, units=units),)


def _advance_to_cell(context):
    """推进到目标格附近，逐单位展开队形。"""
    units = context.subject.agents()
    cell = tuple(context.params["cell"])
    stance = context.params["stance"]
    spread = int(context.params["spread"])
    if not spread:
        return (context.intent(MoveTo, units=units, cell=cell, stance=stance),)
    # 多备 attempt 个候选格：卡住重来时换一个落点，从另一侧靠近目标
    cells = formation_cells(cell, len(units) + max(0, context.attempt),
                            context.observation.map_data,
                            blocked=blocked_cells(context.observation.state))
    if not cells:
        cells = (cell,)
    out = []
    for index, agent in enumerate(units):
        target = cells[(index + context.attempt) % len(cells)]
        out.append(context.intent(MoveTo, units=(agent,), cell=target,
                                  stance=stance))
    return tuple(out)


def _engage_nearest(context):
    """半径内最近的可见敌人，逐单位开火。

    「最近的」是一条无评价的固定规则；要不要接战由调用方通过半径决定。
    """
    radius = float(context.params["radius"])
    enemies = context.observation.visible_enemies
    out = []
    for agent in context.subject.agents():
        mine = context.subject.object_of(agent)
        if mine is None:
            continue
        target = _nearest(mine, enemies, radius)
        target_agent = context.subject.agent_id(target.pointer) if target else None
        if target_agent is None:
            continue
        out.append(context.intent(Attack, units=(agent,), target=target_agent))
    return tuple(out)


def _nearest(mine, enemies, radius):
    """半径内最近的敌人，没有则返回 `None`。"""
    my_cell = mine.coordinates.cell
    best, best_distance = None, None
    for enemy in enemies:
        cell = enemy.coordinates.cell
        dx, dy = cell[0] - my_cell[0], cell[1] - my_cell[1]
        distance = dx * dx + dy * dy
        if distance > radius * radius:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = enemy, distance
    return best


def _hold_and_fire(context):
    """停止这队单位的移动，对半径内最近的可见敌人开火。

    有目标的单位下攻击令、其余下停止令：整队不再推进，武器仍指向开火半径内
    的敌人。半径是开火的界线，更远的敌人不打，免得为追敌又移动起来。
    """
    radius = float(context.params["radius"])
    enemies = context.observation.visible_enemies
    out = []
    for agent in context.subject.agents():
        mine = context.subject.object_of(agent)
        target = _nearest(mine, enemies, radius) if mine is not None else None
        target_agent = (context.subject.agent_id(target.pointer)
                        if target is not None else None)
        if target_agent is None:
            out.append(context.intent(Hold, units=(agent,)))
        else:
            out.append(context.intent(Attack, units=(agent,), target=target_agent))
    return tuple(out)


def _advance_covering(context):
    """组合示范：有敌人先接战，没有敌人再推进。

    `optional=True` 让「没有敌人」时内层静默返回空，而不是报错。
    """
    contact = context.call("engage_nearest", optional=True,
                           radius=context.params["radius"])
    if contact:
        return contact
    return context.call("advance_to_cell", cell=context.params["cell"],
                        stance=context.params["stance"],
                        spread=context.params["spread"])


TACTICS = (
    Tactic(TacticInfo(
        name="hold_position",
        summary="让这队单位原地驻守",
        params=(),
        requires=("has_units",),
    ), _hold),

    Tactic(TacticInfo(
        name="halt",
        summary="停止这队单位；零件，供组合技法调用",
        requires=("has_units",),
        expose=False,
    ), _hold),

    Tactic(TacticInfo(
        name="advance_to_cell",
        summary="把这队单位推进到目标格附近，逐单位展开队形",
        params=(
            Param("cell", REQUIRED, "目标格 (x, y)", is_cell),
            Param("stance", Stance.AGGRESSIVE, "接战姿态：aggressive / passive / hold",
                  is_stance),
            Param("spread", 1, "队形展开；0 表示全去中心格", is_non_negative_int),
        ),
        requires=("has_units", "has_map"),
    ), _advance_to_cell),

    Tactic(TacticInfo(
        name="engage_nearest",
        summary="对半径内最近的可见敌人开火",
        params=(Param("radius", 8, "接战半径（格）", is_positive_number),),
        requires=("has_units", "has_enemies"),
    ), _engage_nearest),

    Tactic(TacticInfo(
        name="hold_and_fire",
        summary="停止这队单位的移动，对半径内最近的可见敌人开火",
        params=(Param("radius", 8, "开火半径（格）；更远的敌人不打，免得追敌移动",
                      is_positive_number),),
        requires=("has_units",),
    ), _hold_and_fire),

    Tactic(TacticInfo(
        name="advance_covering",
        summary="有敌人先接战，没有敌人再推进",
        params=(
            Param("cell", REQUIRED, "目标格 (x, y)", is_cell),
            Param("radius", 8, "接战半径（格）", is_positive_number),
            Param("stance", Stance.AGGRESSIVE, "推进姿态", is_stance),
            Param("spread", 1, "队形展开；0 表示全去中心格", is_non_negative_int),
        ),
        requires=("has_units", "has_map"),
    ), _advance_covering),
)
