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
from ...runtime.intents import Attack, Hold, MoveTo, Stance
from ..core import (REQUIRED, Param, Tactic, TacticInfo, is_bool,
                    is_positive_number)


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
    """集火指定目标：够得着就打，够不着就**开过去打**（`chase`），目标没了则驻守。

    实测一个玩家点了 15 格外的建筑，旧的实现把 4 台坦克**原地驻守**，他不但没打，
    还整体后撤、白松了压力——「点名一个目标」的语义就是去打它，够不着时该走过去，
    而不是站住。要「只打半径内的」就用 `chase=false`，或改用 `engage_nearest`。
    """
    target = int(context.params["target"])
    radius = float(context.params["radius"])
    chase = bool(context.params["chase"])
    enemy = _enemy_of(context, target)
    out = []
    for agent in context.subject.agents():
        mine = context.subject.object_of(agent)
        far = (enemy is not None and mine is not None
               and _distance_sq(mine.coordinates.cell, enemy.coordinates.cell)
               > radius * radius)
        if enemy is None or mine is None:
            out.append(context.intent(Hold, units=(agent,)))
        elif far and chase:
            out.append(context.intent(MoveTo, units=(agent,),
                                      cell=enemy.coordinates.cell,
                                      stance=Stance.AGGRESSIVE))
        elif far:
            out.append(context.intent(Hold, units=(agent,)))
        else:
            out.append(context.intent(Attack, units=(agent,), target=target))
    return tuple(out)


def _guard_area(context):
    """半径内有敌人就打；没有就不下令，让任务留在在管里等下一拍。

    到期（`max_frames`）就转成驻守，任务随之结算、单位交还：这条任务靠"不下令"
    活着，没有边界就会一直占着这些单位。到期由运行时记成 `EXPIRED` 并说明原因。
    """
    limit = context.params["max_frames"]
    since = context.recall("since")
    if since is None:
        context.remember("since", context.frame)
    elif context.frame - since >= limit:
        return tuple(context.intent(Hold, units=(agent,))
                     for agent in context.subject.agents())
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
            # 必填：`target` 默认 0 时是「所有人都驻守」，任务还记成 satisfied——
            # 模型少写一个参数却拿到「成功」，看不出自己其实什么都没打。
            Param("target", REQUIRED, "要打的敌方单位 id，取自 status 的可见敌方",
                  is_positive_number),
            Param("chase", True,
                  "目标在半径外时开过去打（点名的目标默认去追；false 则原地驻守）",
                  is_bool),
            Param("radius", 12, "只在目标这么近时才开火（格）", is_positive_number),
        ),
        requires=("has_units",),
    ), _focus_fire),

    Tactic(TacticInfo(
        name="guard_area",
        summary="持续守住原地：半径内出现敌人就开火，没有目标时不下令、等下一拍；"
                "到期自动转为驻守收工",
        params=(
            Param("radius", 8, "开火半径（格）", is_positive_number),
            Param("max_frames", 3600, "最多守多少游戏帧（60 帧≈1 秒），到点收工驻守",
                  is_positive_number),
        ),
        requires=("has_units",),
        # 自带生命周期：没目标时不下令、等下一拍，到期（`max_frames`）自己转驻守
        # 收工。故不套框架的等待上限，由它自己负责收尾。
        wait_grace_frames=None,
    ), _guard_area),
)
