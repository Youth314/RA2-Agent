"""侦察类技法：去没去过的地方看看。

玩家把侦察归在微操里，而它的难点不在「怎么打」而在**去哪儿**：模型看得到敌人，却
看不到「哪片还没去过」。故这里由技法替它算：从这队单位出发，找最近的**未探索格**，
走过去；到了这一步就结算——再探下一片由模型决定（或下一次调用继续），因为「值不值得
继续往那个方向推」是判断，不是计算。
"""
from ...runtime.intents import MoveTo, Stance
from ..core import (Param, Tactic, TacticInfo, is_non_negative_int, is_positive_int,
                    is_stance)

#: 从这队单位往外搜多远（格）。太小会在基地附近打转，太大会派人横穿整张图。
SCOUT_SEARCH_RADIUS = 60


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


def _scout_area(context):
    """把这队单位派往最近的未探索格。

    默认 `stance=passive`：侦察不是进攻，遇到拦截不该恋战——要打就显式给
    `stance=aggressive`。
    """
    map_data = context.observation.map_data
    units = []
    for agent in context.subject.agents():
        obj = context.subject.object_of(agent)
        if obj is None or obj.in_limbo or obj.is_building:
            continue
        units.append((agent, obj))
    if not units:
        return ()
    cell = nearest_unknown(map_data, _center(units),
                           radius=int(context.params["radius"]))
    if cell is None:
        return ()
    return (context.intent(MoveTo, units=tuple(a for a, _ in units), cell=cell,
                           stance=context.params["stance"]),)


TACTICS = (
    Tactic(TacticInfo(
        name="scout_area",
        summary="把这队单位派往最近的未探索区域；到了就结算，再探哪儿由你决定",
        params=(Param("radius", SCOUT_SEARCH_RADIUS, "往多远处找未探索格（格）",
                      is_positive_int),
                Param("stance", Stance.PASSIVE, "遇敌时的姿态；侦察默认不恋战",
                      is_stance)),
        requires=("has_units", "has_map"),
        idle_ends_task=True,
    ), _scout_area),
)
