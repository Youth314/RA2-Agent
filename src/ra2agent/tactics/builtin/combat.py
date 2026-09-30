"""接战类技法：指定目标集火，以及持续的区域防守。

与 `micro.py` 里那两条的区别在于「目标怎么选」和「任务活多久」：

- `focus_fire` 打**指定 id**，不再让「最近」规则把火力摊到对面充当肉盾的步兵上；
- `guard_area` **持续**在半径内索敌，而 `hold_and_fire` 是脉冲——发一次、单位到位
  即结算释放，之后不再索敌。

`guard_area` 的做法是：**没有目标的单位不下任何令**。这些单位因此一直停在「待下令」
状态（`UnitMode.MOVING` 且无目标），任务不结算，于是下一拍还会调这条技法来看一眼；
敌人一进半径就开火，目标没了会退回待下令状态再自动换目标。代价是这条任务会一直
挂在「在管」里占着单位，收尾要靠 `cancel` 或调用时给 `ttl_frames`。

先 `hold_position` 让它们停下、再 `guard_area` 守住，是这对技法的正常用法：前者的
任务结算后单位交还，后者只负责开火，不会再让它们挪窝。
"""
from ...intents import Attack, Hold
from ..core import Param, Tactic, TacticInfo, is_positive_number


def _distance_sq(one, other):
    """两格的平方距离；比较半径时省一次开方。"""
    dx, dy = one[0] - other[0], one[1] - other[1]
    return dx * dx + dy * dy


def _enemy_of(context, agent_id):
    """按 agent id 在当前可见敌人里找对象；看不见就给 `None`。"""
    for enemy in context.observation.visible_enemies:
        if context.subject.agent_id(enemy.pointer) == agent_id:
            return enemy
    return None


def _nearest(mine, enemies, radius):
    """半径内最近的敌人，没有则 `None`。"""
    my_cell = mine.coordinates.cell
    best, best_distance = None, None
    for enemy in enemies:
        distance = _distance_sq(enemy.coordinates.cell, my_cell)
        if distance > radius * radius:
            continue
        if best_distance is None or distance < best_distance:
            best, best_distance = enemy, distance
    return best


def _focus_fire(context):
    """集火指定目标；够不着和目标没了的单位原地驻守，任务随之收尾。"""
    target = int(context.params["target"])
    radius = float(context.params["radius"])
    enemy = _enemy_of(context, target)
    out = []
    for agent in context.subject.agents():
        mine = context.subject.object_of(agent)
        if (enemy is None or mine is None
                or _distance_sq(mine.coordinates.cell, enemy.coordinates.cell)
                > radius * radius):
            out.append(context.intent(Hold, units=(agent,)))
            continue
        out.append(context.intent(Attack, units=(agent,), target=target))
    return tuple(out)


def _guard_area(context):
    """半径内有敌人就打；没有就不下令，让任务留在在管里等下一拍。"""
    radius = float(context.params["radius"])
    enemies = context.observation.visible_enemies
    out = []
    for agent in context.subject.agents():
        mine = context.subject.object_of(agent)
        if mine is None:
            continue
        target = _nearest(mine, enemies, radius)
        target_agent = (context.subject.agent_id(target.pointer)
                        if target is not None else None)
        if target_agent is None:
            continue
        out.append(context.intent(Attack, units=(agent,), target=target_agent))
    return tuple(out)


TACTICS = (
    Tactic(TacticInfo(
        name="focus_fire",
        summary="集火指定的敌方 id；半径外或目标已消失的单位原地驻守",
        params=(
            Param("target", 0, "要打的敌方单位 id，取自 status 的可见敌方", None),
            Param("radius", 12, "只在目标这么近时才开火（格）", is_positive_number),
        ),
        requires=("has_units",),
    ), _focus_fire),

    Tactic(TacticInfo(
        name="guard_area",
        summary="持续守住原地：半径内出现敌人就开火，没有目标时不下令、等下一拍",
        params=(Param("radius", 8, "开火半径（格）", is_positive_number),),
        requires=("has_units",),
    ), _guard_area),
)
