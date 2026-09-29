"""发送前校验。

越界坐标会崩溃游戏且引擎不报错，因此校验必须在本地完成。规则与实测依据见
`.agents/notes/命令接口源码结论.md#前置校验清单` 与
`.agents/notes/命令能力测绘结果.md#校验层`。

本模块只拒绝；不做任何修补或降级——能否换一条路走由调用方决定。
"""
from .constants import (LEPTONS_PER_CELL, MISSIONS_ILLEGAL_FOR_UNIT_ORDER,
                        UNIT_ACTIONS_IMPLEMENTED, UNIT_ACTIONS_NEED_CELL,
                        UNIT_ACTIONS_NEED_TARGET, UnitAction)
from .errors import InvalidCommand
from .state import Coordinates, GameObject, GameState, MapData


class Validator:
    """对一帧观测与一张地图做校验。

    地图用于坐标校验；未提供地图时坐标类校验一律拒绝，而不是放行——放行的
    代价是游戏崩溃。
    """

    def __init__(self, map_data: MapData | None = None,
                 allow_foreign: bool = False):
        self.map_data = map_data
        self.allow_foreign = allow_foreign

    def with_map(self, map_data: MapData) -> "Validator":
        """返回一个带地图、其余策略相同的新校验器。"""
        return Validator(map_data, allow_foreign=self.allow_foreign)

    # ------------------------------------------------------------ 坐标
    def check_coordinates(self, coordinates: Coordinates) -> None:
        """坐标必须落在地图内，且不触发 `Coord2Cell` 的 short 回绕。

        `Coord2Cell` 把世界坐标除以 256 后截断为 `short`，越界值会回绕成看似
        合法的格。上界 `width * 256` 同时排除了回绕：地图宽度远小于 `short`
        上限，故范围内的商不可能溢出。
        """
        if self.map_data is None:
            raise InvalidCommand("尚未取得地图，无法校验坐标")
        limit_x = self.map_data.width * LEPTONS_PER_CELL
        limit_y = self.map_data.height * LEPTONS_PER_CELL
        if not 0 <= coordinates.x < limit_x:
            raise InvalidCommand(
                f"x={coordinates.x} 越界，合法范围 [0, {limit_x})")
        if not 0 <= coordinates.y < limit_y:
            raise InvalidCommand(
                f"y={coordinates.y} 越界，合法范围 [0, {limit_y})")
        cell_x, cell_y = coordinates.cell
        if not self.map_data.in_bounds(cell_x, cell_y):
            raise InvalidCommand(
                f"({coordinates.x},{coordinates.y}) 落到格 ({cell_x},{cell_y})，"
                f"超出 {self.map_data.width}x{self.map_data.height} 的地图")

    # ------------------------------------------------------------ 对象
    def check_state(self, state) -> None:
        """校验需要一帧观测。"""
        if not isinstance(state, GameState):
            raise InvalidCommand("需要一帧 GameState 才能校验")

    def resolve(self, state: GameState, units) -> list[GameObject]:
        """把指针列表解析为对象，并确认存在且不处于 limbo。"""
        self.check_state(state)
        pointers = _as_pointers(units)
        if not pointers:
            raise InvalidCommand("对象列表为空")
        resolved = []
        for pointer in pointers:
            found = state.object(pointer)
            if found is None:
                raise InvalidCommand(f"对象 {pointer} 不在当前状态中")
            if found.in_limbo:
                raise InvalidCommand(f"对象 {pointer} 处于 limbo")
            resolved.append(found)
        return resolved

    def check_mission(self, objects) -> None:
        """`UnitOrder` 会拒绝处于特定任务的对象。

        刚放置的建筑仍在 `Mission_Construction`，此时任何 `UnitOrder` 都会被
        拒；这类对象应改走 `ClickEvent`。
        """
        for obj in objects:
            if obj.mission in MISSIONS_ILLEGAL_FOR_UNIT_ORDER:
                raise InvalidCommand(
                    f"对象 {obj.pointer} 的 mission={obj.mission} 非法，"
                    f"UnitOrder 会拒绝；对象级网络事件请改用 ClickEvent")

    def check_ownership(self, state: GameState, objects) -> None:
        """拒绝指挥非己方对象。

        引擎不做这项检查：`UnitOrder` 在全局对象表里按指针查对象，查到即调
        `ClickMission`，全程不看归属，因此敌方与中立单位同样能下令。生产与建造
        倒是固定归属当前玩家，因为那条路走 `add_event`。

        「Agent 即玩家」要求适配层自己强制这条约束，否则等于可以操纵全场。需要
        越权（调试、导演模式、全局观察者）时把 `allow_foreign` 置真，使其显式。
        """
        if self.allow_foreign:
            return
        house = state.player_house()
        for obj in objects:
            if obj.house != house.pointer:
                raise InvalidCommand(
                    f"对象 {obj.pointer} 属于阵营 {obj.house}，不是己方 "
                    f"{house.pointer}；引擎不拦此类越权，故在此拒绝。"
                    f"确需越权请显式设置 allow_foreign")

    def check_action(self, action) -> None:
        """动作必须在服务端已实现。"""
        if action not in UNIT_ACTIONS_IMPLEMENTED:
            raise InvalidCommand(
                f"action={int(action)} 未实现，服务端会抛 invalid unit action")

    # ------------------------------------------------------------ 组合
    def check_unit_order(self, state: GameState, units, action,
                         target_object=None, coordinates=None) -> None:
        """校验一条 `UnitOrder` 的全部前置条件。"""
        self.check_action(action)
        if action == UnitAction.SELL_CELL:
            if coordinates is None:
                raise InvalidCommand("SELL_CELL 需要 coordinates")
            self.check_coordinates(coordinates)
            return
        resolved = self.resolve(state, units)
        self.check_ownership(state, resolved)
        self.check_mission(resolved)
        if action in UNIT_ACTIONS_NEED_TARGET and not target_object:
            raise InvalidCommand(f"action={int(action)} 需要 target_object")
        if action in UNIT_ACTIONS_NEED_CELL and coordinates is None:
            raise InvalidCommand(f"action={int(action)} 需要 coordinates")
        if coordinates is not None:
            self.check_coordinates(coordinates)

    def check_place(self, coordinates: Coordinates) -> None:
        """校验建筑放置坐标。合法性由引擎判定，本层只挡越界。"""
        self.check_coordinates(coordinates)


def _as_pointers(units) -> list[int]:
    """接受指针或对象，统一取指针。"""
    out = []
    for item in units:
        out.append(item.pointer if isinstance(item, GameObject) else int(item))
    return out
