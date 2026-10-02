"""接战类技法：指定目标集火，以及持续的区域防守。

与 `micro.py` 里那两条的区别在于「目标怎么选」和「任务活多久」：

- `focus_fire` 打**指定 id**，不再让「最近」规则把火力摊到对面充当肉盾的步兵上；
- `guard_area` 无目标时留在管理中等待索敌；`hold_and_fire` 无目标时发旧 Hold，
  有目标时发 Attack，攻击分支沿用运行时的接战生命周期。

`guard_area` 的做法是：**没有目标的单位不下任何令**。这些单位因此一直停在「待下令」
状态（`UnitMode.MOVING` 且无目标），任务不结算，于是下一拍还会调这条技法来看一眼；
敌人一进半径就开火，目标没了会退回待下令状态再自动换目标。代价是这条任务会一直
挂在「在管」里占着单位，收尾要靠 `cancel` 或调用时给 `ttl_frames`。

`hold_position` 只是旧 STOP 兼容入口；`guard_area` 的 Attack 可能追击，二者均不
保证永久保持位置。技法内的到期检查还依赖再次求值，接战中不保证准时收尾。
"""
from ...runtime.intents import Attack, GuardCurrent, GuardPosition, Hold, MoveTo, Stance
from ..core import (REQUIRED, Param, Tactic, TacticInfo, is_bool,
                    is_optional_cell, is_positive_number)


def _native_guard(context):
    """一次原版警戒输入；单位数量、身份与适用性统一由 L0 校验。"""
    units = context.subject.agents()
    cell = context.params["cell"]
    if cell is None:
        return (context.intent(GuardCurrent, units=units),)
    return (context.intent(GuardPosition, units=units, cell=cell),)


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
    """集火指定目标：半径内发 Attack，半径外按 chase 推进或发旧 Hold。

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

    再次求值时若已到期（`max_frames`）就发旧 Hold 收尾；接战状态可能延后求值，
    因此这里的上限不是运行时硬截止时间。
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
        name="native_guard",
        summary="向单个己方车辆提交一次原生警戒；省略 cell 等同 G，提供 cell 为地点警戒；"
                "回执只确认输入，随后释放租约，不保证到达、持续保护或维修，cancel 不停止原生行为",
        params=(Param("cell", None, "可选地点 (x, y)；不填则在执行时的当前位置警戒",
                      is_optional_cell),),
        requires=("has_units", "has_map", "guard_v1"),
    ), _native_guard),

    Tactic(TacticInfo(
        name="focus_fire",
        summary="集火指定的可见敌方 id；半径外默认向目标推进，chase=false 或目标消失时发旧 STOP",
        params=(
            # 必填：`target` 默认 0 时是「所有人都驻守」，任务还记成 satisfied——
            # 模型少写一个参数却拿到「成功」，看不出自己其实什么都没打。
            Param("target", REQUIRED, "要打的敌方单位 id，取自 status 的可见敌方",
                  is_positive_number),
            Param("chase", True,
                  "目标在半径外时向目标推进；false 则发旧 STOP；追近后的连续攻击尚有生命周期限制",
                  is_bool),
            Param("radius", 12, "只在目标这么近时才开火（格）", is_positive_number),
        ),
        requires=("has_units",),
    ), _focus_fire),

    Tactic(TacticInfo(
        name="guard_area",
        summary="半径内选敌攻击，可能追击；无目标时不下令并等待索敌；再次求值发现到期才发旧 STOP 收尾",
        params=(
            Param("radius", 8, "开火半径（格）", is_positive_number),
            Param("max_frames", 3600, "到期检查阈值（游戏帧）；接战中可能延后检查，不是硬截止时间",
                  is_positive_number),
        ),
        requires=("has_units",),
        # 没目标时继续等待；再次求值才检查 max_frames，接战中可能延后。
        # 当前不套框架等待上限，不能将此配置解释为硬截止时间。
        wait_grace_frames=None,
    ), _guard_area),
)
