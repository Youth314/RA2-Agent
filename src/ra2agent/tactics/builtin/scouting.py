"""侦察类技法：去没去过的地方看看。

玩家把侦察归在微操里，而它的难点不在「怎么打」而在**去哪儿**：模型看得到敌人，却
看不到「哪片还没去过」。故这里由技法替它算：每拍给每台单位找它最近的**未探索格**
走过去，直到这一带探完或到期，才转驻守收工。

**持续而非一次**：实测两个玩家都报过「狗到达后停住不动，要自己再下 `advance_to_cell`，
而那条只能给格、换不了方向」——一次一跳等于把找路的活又推回给模型。这里的生命周期与
`guard_area` 同一套：该下令时下令、不该下令时不下令，故**必须自己带上限**
（`max_frames`，并把 `wait_grace_frames` 设为 `None` 豁免运行时的等待收割）。
"""
from ...constants import Mission
from ...runtime.intents import Hold, MoveTo, Stance
from ..core import (Param, Tactic, TacticInfo, is_positive_int, is_stance)

#: 同一台单位派往同一格的最短间隔，免得每拍重发同一条移动令把它钉在原地。
REPEAT_EVERY_FRAMES = 300

#: 处于这些任务就算「正在路上」，不再重复下令。
MOVING_MISSIONS = (Mission.MOVE, Mission.QMOVE, Mission.ATTACK_MOVE,
                   Mission.PATROL)

#: 从这队单位往外搜多远（格）。太小会在基地附近打转，太大会派人横穿整张图。
SCOUT_SEARCH_RADIUS = 60

#: 一条侦察任务的默认寿命（游戏帧，60 帧≈1 秒）。到点转驻守，单位交还。
SCOUT_MAX_FRAMES = 3600


def _center(units):
    """这队单位的中心格。"""
    cells = [obj.coordinates.cell for _agent, obj in units]
    return (sum(c[0] for c in cells) // len(cells),
            sum(c[1] for c in cells) // len(cells))


def nearest_unknown(map_data, cell, *, radius=SCOUT_SEARCH_RADIUS):
    """离 `cell` 最近的未探索格；半径内都探过了就给 `None`。

    逐圈由近及远，与找矿同一套路：近处没探过就先探近处。
    """
    if map_data is None:
        return None
    for step in range(0, radius + 1):
        best = None
        for x, y in _ring(cell, step):
            if not map_data.in_bounds(x, y) or map_data.is_explored(x, y):
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


def _hold_all(context):
    """收工：全体驻守，任务随之结算、单位交还。"""
    return tuple(context.intent(Hold, units=(agent,))
                 for agent in context.subject.agents())


def _scout_area(context):
    """持续侦察：每拍把还没在路上的单位派往它最近的未探索格。

    都没得探了（`nearest_unknown` 给 `None`）或到期，就全体驻守收工。返回空元组
    表示「都还在路上」——那时不下令，靠运行时的等待逻辑挂着（故豁免等待收割）。
    """
    limit = int(context.params["max_frames"])
    since = context.recall("since")
    if since is None:
        context.remember("since", context.frame)
    elif context.frame - since >= limit:
        return _hold_all(context)
    map_data = context.observation.map_data
    radius = int(context.params["radius"])
    stance = context.params["stance"]
    recent = dict(context.recall("recent") or {})
    moving = 0
    out = []
    for agent in context.subject.agents():
        obj = context.subject.object_of(agent)
        if obj is None or obj.in_limbo or obj.is_building:
            continue
        cell = nearest_unknown(map_data, obj.coordinates.cell, radius=radius)
        if cell is None:
            continue                     # 这一台周围探完了，让它待着
        moving += 1
        when, cell_was = recent.get(obj.pointer, (None, None))
        if (cell_was == cell
                and (obj.mission in MOVING_MISSIONS
                     or (when is not None
                         and context.frame - when < REPEAT_EVERY_FRAMES))):
            continue                     # 已经在去那儿的路上了
        recent[obj.pointer] = (context.frame, cell)
        out.append(context.intent(MoveTo, units=(agent,), cell=cell, stance=stance))
    if out:
        context.remember("recent", recent)
    if not out and moving == 0:
        return _hold_all(context)        # 这一带都探过了，收工驻守
    return tuple(out)


TACTICS = (
    Tactic(TacticInfo(
        name="scout_area",
        summary="持续侦察：不断派往最近的未探索区域，探完或到期转驻守",
        params=(Param("radius", SCOUT_SEARCH_RADIUS, "往多远处找未探索格（格）",
                      is_positive_int),
                Param("stance", Stance.PASSIVE, "遇敌时的姿态；侦察默认不恋战",
                      is_stance),
                Param("max_frames", SCOUT_MAX_FRAMES,
                      "最多探多少游戏帧（60 帧≈1 秒），到点转驻守收工",
                      is_positive_int)),
        requires=("has_units", "has_map"),
        # 自带生命周期：探完或到期自己转驻守，故豁免运行时的等待收割
        wait_grace_frames=None,
    ), _scout_area),
)
