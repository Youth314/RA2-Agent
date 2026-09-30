"""建造类技法：把完工的建筑放到地上。

`place_ready_building` 依赖 R1（limbo 对象可寻址）：完工待放置的建筑在观测里
`in_limbo=True`，不在 `observation.own` 里，只有 `UnitPool.agent_id()` 能把它
翻成 agent id，而 `Place.building` 只收 agent id。

落点给不给都行：

- 给了 `cell` 就用它——`status` 的「可选落点」是 `PlaceQuery` 的实测结果，最稳；
- 不给就按「围着待放建筑找一格空地」兜底，让模型不在场时（自动触发、或模型只写了
  一句「造电厂」）建筑也能落地。引擎的合法落点只有它自己说了算，技法不做 I/O，
  拿不到那份结果；兜底格若不合规，`Validator.check_place` 会拦下，不会错放。

`units` 参数照旧要点名己方单位（框架要求），待放建筑自己不在池子里、点不了它。
"""
from ...formation import blocked_cells, formation_cells
from ...intents import Place
from ..core import (REQUIRED, Param, Tactic, TacticInfo, is_optional_cell)


def _ready_building(context):
    """完工待放置的那一栋：返回 `(agent id, 它所在格)`；没有则 `None`。"""
    state = context.observation.state
    if state is None:
        return None
    for factory in state.own_factories():
        if not factory.completed:
            continue
        building = state.object(factory.object)
        if building is None:
            continue
        agent = context.subject.agent_id(factory.object)
        if agent is None:
            continue
        return agent, tuple(building.coordinates.cell)
    return None


def _fallback_cell(context, center):
    """围着待放建筑找最近的一格空地；地图拿不到时给 `None`。

    待放建筑自己报的坐标要排除掉：它还在 limbo 里、`blocked_cells` 不算它，
    否则最近的候选永远是它自己那一格。
    """
    map_data = context.observation.map_data
    if map_data is None:
        return None
    blocked = set(blocked_cells(context.observation.state))
    blocked.add(tuple(center))
    cells = formation_cells(center, 1, map_data, blocked=blocked)
    return cells[0] if cells else None


def run(context):
    """把已完工的建筑放到给定格；没给格就自己找一格。"""
    found = _ready_building(context)
    if found is None:
        return ()
    agent, center = found
    cell = context.params.get("cell")
    if cell is None:
        cell = _fallback_cell(context, center)
        if cell is None:
            return ()
    return (context.intent(Place, building=agent, cell=tuple(cell)),)


TACTICS = (
    Tactic(TacticInfo(
        name="place_ready_building",
        summary="把已完工待放置的建筑放下；cell 不给就自己找一格空地",
        params=(Param("cell", None, "落点格 (x, y)，取自 status 的可选落点；不填则自动找",
                      is_optional_cell),),
        requires=("has_pending_building",),
    ), run),
)
