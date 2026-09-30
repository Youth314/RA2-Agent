"""建造类技法：把完工的建筑放到地上。

`place_ready_building` 依赖 R1（limbo 对象可寻址）：完工待放置的建筑在观测里
`in_limbo=True`，不在 `observation.own` 里，只有 `UnitPool.agent_id()` 能把它
翻成 agent id，而 `Place.building` 只收 agent id。

落点给不给都行：

- 给了 `cell` 就用它——`status` 的「可选落点」是 `PlaceQuery` 的实测结果，最稳；
- 不给就**交给 L0**：`Place.cell=None` 让执行器拿 `PlaceQuery` 问出一格最近的合法
  落点。建筑能不能放只有引擎说了算，而技法不做 I/O，本地算出来的「空地」会被
  `CanPlaceHere` 拦下（实测兜底格给出 `格=(1,0)`、被 `Proximity check failed` 拒），
  故这里不再自己猜格。

`units` 参数照旧要点名己方单位（框架要求），待放建筑自己不在池子里、点不了它。
"""
from ...runtime.intents import Place
from ..core import (Param, Tactic, TacticInfo, is_optional_cell)


def _ready_building(context):
    """完工待放置的那一栋的 agent id；没有则 `None`。"""
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
        return agent
    return None


def run(context):
    """把已完工的建筑放到给定格；没给格就交给 L0 问引擎要一格。"""
    agent = _ready_building(context)
    if agent is None:
        return ()
    cell = context.params.get("cell")
    return (context.intent(Place, building=agent,
                           cell=None if cell is None else tuple(cell)),)


TACTICS = (
    Tactic(TacticInfo(
        name="place_ready_building",
        summary="把已完工待放置的建筑放下；cell 不给就由 L0 问引擎要一格合法落点",
        params=(Param("cell", None, "落点格 (x, y)，取自 status 的可选落点；不填由 L0 找",
                      is_optional_cell),),
        requires=("has_pending_building",),
    ), run),
)
