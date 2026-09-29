"""队形展开：把目标格摊成若干个可站立的格。

纯计算，无状态，技法与运行时共用。只排除明显的不可站立格（越界、未探索、水、
岩石、墙、已有建筑），具体能否走到由引擎寻路决定——技法只负责选目标格。
"""
from .constants import LandType
from .state import GameState, MapData

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
