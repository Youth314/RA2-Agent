"""队形展开：把目标格摊成若干个可站立的格。

纯计算，无状态，技法与运行时共用。只排除明显的不可站立格（越界、未探索、水、
岩石、墙、已有建筑），具体能否走到由引擎寻路决定——技法只负责选目标格。
"""
from ..constants import LandType
from ..engine.state import GameState, MapData, cell_center

#: 队形展开搜索的默认半径（格）。
DEFAULT_SPREAD_RADIUS = 4

#: 单位不能站立的地形。
IMPASSABLE = frozenset({LandType.WATER, LandType.ROCK, LandType.WALL})


def blocked_cells(state: GameState) -> frozenset:
    """已有建筑占住的格。

    只算建筑：单位会挪窝，把它们当障碍会让队形每帧都变。
    """
    cells = set()
    for obj in state.objects:
        if obj.is_building and not obj.in_limbo:
            cells.add(obj.coordinates.cell)
    return frozenset(cells)


def formation_cells(center, count, map_data: MapData, blocked=(),
                    radius=DEFAULT_SPREAD_RADIUS) -> tuple:
    """围绕 `center` 挑 `count` 个可站立的格，由近及远。

    候选按「到中心的切比雪夫距离、欧氏距离、行、列」排序，保证同样输入得到同样
    结果。候选不够时返回已有部分，调用方自行决定退路（通常是全去中心格）。
    """
    if count <= 0:
        return ()
    if map_data is None:
        raise ValueError("队形展开需要地图")
    column, row = center
    blocked = frozenset(blocked)
    candidates = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            x, y = column + dx, row + dy
            if (x, y) in blocked or not map_data.in_bounds(x, y):
                continue
            if map_data.shrouded(x, y):
                continue
            if map_data.land_type(x, y) in IMPASSABLE:
                continue
            candidates.append((max(abs(dx), abs(dy)), dx * dx + dy * dy, y, x))
    candidates.sort()
    return tuple((x, y) for _, _, y, x in candidates[:count])


def place_candidates(centers, map_data, *, radius=DEFAULT_SPREAD_RADIUS,
                     limit=None) -> list:
    """由近及远铺开建筑放置的候选格，返回世界坐标。

    `PlaceQuery` 收的是候选**输入**，只返回其中合法的子集，故候选给得越密越好；
    条数上限由 `limit` 兜住（`PLACE_QUERY_MAX_LENGTH`，超出服务端静默截断）。地图
    外的格一律不发出去——越界坐标会崩游戏。

    与 `formation_cells` 的分工：那个筛「单位站得住」，这个不做地形判断——建筑
    能不能放只有引擎说了算，候选给回去让它自己挑。
    """
    if limit is not None and limit <= 0:
        return []
    out = []
    seen = set()
    for base_x, base_y in centers:
        for ring in range(radius + 1):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    x, y = base_x + dx, base_y + dy
                    if (x, y) in seen:
                        continue
                    if map_data is not None and not map_data.in_bounds(x, y):
                        continue
                    seen.add((x, y))
                    out.append(cell_center(x, y))
                    if limit is not None and len(out) >= limit:
                        return out
    return out
