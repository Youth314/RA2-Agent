"""内置技法：首批示范。

五条暴露给模型，一条只供组合调用。它们只做「按当前局面产出意图」这一件事：
不记状态、不判失败、不重试——那些是运行时的活，见 `ra2agent/micro.py`。
"""
from ...data.catalogue import own_building_cells
from ...runtime.formation import blocked_cells, formation_cells
from ...runtime.intents import Attack, Hold, MoveTo, Stance, Stop
from ..core import (REQUIRED, Param, Tactic, TacticInfo, is_cell,
                    is_non_negative_int, is_optional_cell, is_positive_number,
                    is_stance)


def _stop(context):
    """单车辆玩家输入；完整适用性由 L0 复查。"""
    return (context.intent(Stop, units=context.subject.agents()),)


def _hold(context):
    """旧 Mission_Stop 兼容入口；一次提交，不保证永久驻守。"""
    units = context.subject.agents()
    return (context.intent(Hold, units=units),)


def _halt(context):
    """组合零件复用正式 Stop 技法及其门控，不降级为旧 Hold。"""
    return context.call("stop")


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
    """半径内选敌发 Attack，无目标则发旧 Hold；攻击可能追击。"""
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


def _home_cell(context):
    """「家」在哪：己方建筑的中心格；一栋都没有就 `None`。"""
    cells = own_building_cells(context.observation.state)
    if not cells:
        return None
    return (sum(c[0] for c in cells) // len(cells),
            sum(c[1] for c in cells) // len(cells))


def _retreat(context):
    """脱离接触：退回基地或指定格，路上不恋战。

    默认 `stance=passive`——撤退的意义就是别回头打。不给 `cell` 时退回己方建筑的
    中心格，这是「回防」最常用的落点。
    """
    cell = context.params.get("cell")
    if cell is None:
        cell = _home_cell(context)
        if cell is None:
            return ()
    return (context.intent(MoveTo, units=context.subject.agents(),
                           cell=tuple(cell), stance=context.params["stance"]),)


TACTICS = (
    Tactic(TacticInfo(
        name="stop",
        summary="Stop v1：向单个己方车辆提交一次玩家 S 输入；Grizzly 移动中断与静止输入已验，其他型号未验；"
                "输入确认后释放租约，不保证永久停车或禁火",
        requires=("has_units", "has_map", "stop_v1"),
    ), _stop),

    Tactic(TacticInfo(
        name="hold_position",
        summary="向这队单位提交一次旧 STOP；不承诺玩家 S 等价、永久驻守或禁火",
        params=(),
        requires=("has_units",),
    ), _hold),

    Tactic(TacticInfo(
        name="halt",
        summary="Stop v1 单车辆停止零件，经 stop 提交一次玩家 S 输入；Grizzly 已验，其他型号未验；"
                "输入确认后释放租约，不保证永久停车或禁火",
        requires=("has_units", "has_map", "stop_v1"),
        expose=False,
        version=2,
    ), _halt),

    Tactic(TacticInfo(
        name="advance_to_cell",
        summary="把这队单位推进到目标格附近，逐单位展开队形",
        params=(
            Param("cell", REQUIRED, "目标格 (x, y)", is_cell),
            Param("stance", Stance.AGGRESSIVE,
                  "接战姿态。aggressive＝**遇到敌人会追**，可能被拽离目标格、甚至被拖进"
                  "敌人建筑群的射程里；只想走到位置、不追敌就用 passive；hold 忽略目标格，"
                  "仅发送旧 STOP，不保证永久不动或禁火",
                  is_stance),
            Param("spread", 1, "队形展开；0 表示全去中心格", is_non_negative_int),
        ),
        requires=("has_units", "has_map", "cell_passable"),
    ), _advance_to_cell),

    Tactic(TacticInfo(
        name="engage_nearest",
        summary="对半径内最近的可见敌人开火",
        params=(Param("radius", 8, "接战半径（格）", is_positive_number),),
        requires=("has_units", "has_enemies"),
    ), _engage_nearest),

    Tactic(TacticInfo(
        name="hold_and_fire",
        summary="对半径内最近的可见敌人发攻击令，无目标时发旧 STOP；攻击可能追击，不保证驻守",
        params=(Param("radius", 8, "选敌半径（格）；不限制攻击令发出后的追击距离",
                      is_positive_number),),
        requires=("has_units",),
    ), _hold_and_fire),

    Tactic(TacticInfo(
        name="retreat",
        summary="脱离接触退回基地（或指定格），路上不恋战",
        params=(Param("cell", None, "退到哪一格；不给就退回己方建筑的中心",
                      is_optional_cell),
                Param("stance", Stance.PASSIVE, "撤退路上的姿态，默认不接战",
                      is_stance)),
        requires=("has_units", "has_map"),
    ), _retreat),

    Tactic(TacticInfo(
        name="advance_covering",
        summary="有敌人先接战，没有敌人再推进",
        params=(
            Param("cell", REQUIRED, "目标格 (x, y)", is_cell),
            Param("radius", 8, "接战半径（格）", is_positive_number),
            Param("stance", Stance.AGGRESSIVE,
                  "推进姿态。aggressive＝路上遇敌会追（实测有玩家因此被拽到敌方建筑群里"
                  "送掉 4 台）；只想推进到位置就用 passive；guard_area 的攻击仍可能追击", is_stance),
            Param("spread", 1, "队形展开；0 表示全去中心格", is_non_negative_int),
        ),
        requires=("has_units", "has_map", "cell_passable"),
    ), _advance_covering),
)
