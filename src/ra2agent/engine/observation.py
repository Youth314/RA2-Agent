"""尊重迷雾的观测。

「Agent 即玩家」是设计支柱之一：Agent 只能看到其阵营在当前迷雾下可见的信息。
本模块维护底图与迷雾，并据此过滤对象，向上层只暴露它「看得见」的世界。

观测模型见 `.agents/notes/引擎/命令能力测绘结果.md#观测模型`：

- `GetGameState` 每帧返回对象全量，但**不含地图**，且 `GameState.map_data` 从不填充。
- 完整地图经 `ReadValue{map_data_soa}` 取一次，之后按 `GameState.cells_difference`
  增量维护；该增量带 `index` 与 `shrouded`。

迷雾的语义与限制见「可见性」一节。
"""
from dataclasses import dataclass, field, replace

from ..constants import AbstractType
from .events import EventLog
from .identity import IdentityTable
from .state import GameObject, GameState, House, MapData, TypeTable


@dataclass(frozen=True)
class ObservedTarget:
    """合法当前目标；不证明输入、开火或任务完成，不含 native 地址。"""

    status: str
    agent_id: int | None = None


@dataclass
class Observation:
    """一帧经过迷雾过滤的观测。

    只包含 Agent 阵营「看得见」的内容。`own` 是己方对象——己方永远可见，不
    受迷雾约束。
    """

    frame: int
    house: House
    own: tuple[GameObject, ...] = ()
    visible_enemies: tuple[GameObject, ...] = ()
    neutral: tuple[GameObject, ...] = ()
    state: GameState | None = field(default=None, repr=False)
    map_data: MapData | None = field(default=None, repr=False)
    #: 对象类型表。不随迷雾变化（类型定义是公开知识），故整局共用一份。
    types: TypeTable | None = field(default=None, repr=False)
    #: 可造目录（前提 / 造价 / 科技等级）。同样是公开知识，整局共用一份。
    catalogue: object | None = field(default=None, repr=False)
    #: 己方 actor 的 Agent ID → 当帧合法目标，旧 DLL 为 not_provided。
    actual_targets: dict[int, ObservedTarget] = field(default_factory=dict)

    @property
    def units(self) -> tuple[GameObject, ...]:
        """己方载具。"""
        return tuple(o for o in self.own
                     if o.object_type == AbstractType.UNIT and not o.in_limbo)

    @property
    def infantry(self) -> tuple[GameObject, ...]:
        """己方步兵。"""
        return tuple(o for o in self.own
                     if o.object_type == AbstractType.INFANTRY and not o.in_limbo)

    @property
    def buildings(self) -> tuple[GameObject, ...]:
        """己方建筑。"""
        return tuple(o for o in self.own
                     if o.object_type == AbstractType.BUILDING and not o.in_limbo)

    def summary(self) -> str:
        """一行摘要，用于日志与人工检查。"""
        country = f"（{self.house.faction}）" if self.house.faction else ""
        return (f"帧 {self.frame}｜{self.house.name}{country}｜金 {self.house.money}｜"
                f"己方 {len(self.own)}（载具 {len(self.units)} 步兵 "
                f"{len(self.infantry)} 建筑 {len(self.buildings)}）｜"
                f"可见敌方 {len(self.visible_enemies)}")


class Observer:
    """维护底图、迷雾与对象标识，产出 `Observation`。

    用法：先 `bootstrap()` 取底图与类型表，之后每次 `poll()` 读一帧。
    """

    def __init__(self, client, identity=None, map_data=None, types=None,
                 catalogue=None):
        self.client = client
        self.identity = identity or IdentityTable()
        self.map_data = map_data
        self.types = types
        #: 可造目录。`mcp` 起服务时挂上，条件与 `status` 都读它。
        self.catalogue = catalogue
        self.last_state: GameState | None = None
        #: 事件队列。挂在 `poll()` 上，故 `tick()` 与 `status()` 共享同一份。
        self.events = EventLog()

    # ------------------------------------------------------------ 初始化
    def bootstrap(self) -> "Observer":
        """取完整地图与对象类型表。两者都只取一次。"""
        if self.map_data is None:
            self.map_data = self.client.read_map()
        if self.types is None:
            self.types = self.client.read_object_types()
        return self

    # ------------------------------------------------------------ 每帧
    def poll(self) -> Observation:
        """读一帧，维护迷雾与标识，返回过滤后的观测。"""
        state = self.client.get_state()
        self.absorb(state)
        observation = self.observe(state)
        self.events.update(observation)
        return observation

    def absorb(self, state: GameState) -> int:
        """把一帧的增量并入底图并推进标识表，返回回填的格数。"""
        self.last_state = state
        updated = 0
        if self.map_data is not None and state.cells_difference:
            updated = self.map_data.apply_all(state.cells_difference)
        self.identity.update(state)
        return updated

    def observe(self, state: GameState | None = None) -> Observation:
        """把一帧过滤为观测，不读取也不修改状态。"""
        state = state or self.last_state
        if state is None:
            raise ValueError("尚无观测，请先 poll 或 absorb")
        house = state.player_house()
        own, enemies, neutral = [], [], []
        for obj in state.objects:
            if obj.in_limbo:
                continue
            if obj.house == house.pointer:
                own.append(obj)
            elif not self.is_visible(obj):
                continue
            elif self._is_neutral(state, obj):
                neutral.append(obj)
            else:
                enemies.append(obj)
        legal = {obj.pointer: obj for obj in (*own, *enemies, *neutral)
                 if obj.on_map and obj.health > 0}
        targets = {}
        for actor in own:
            agent = self.identity.agent_id(actor.pointer)
            if agent is not None:
                targets[agent] = self._actual_target(state, actor, legal)
        # Raw target references must not accompany GameObjects exposed to L1.
        clean = lambda objects: tuple(replace(obj, actual_target=None)
                                      if obj.actual_target is not None else obj
                                      for obj in objects)
        return Observation(frame=state.frame, house=house, own=clean(own),
                           visible_enemies=clean(enemies), neutral=clean(neutral),
                           state=state, map_data=self.map_data, types=self.types,
                           catalogue=self.catalogue, actual_targets=targets)

    def _actual_target(self, state, actor, legal):
        raw = actor.actual_target
        if state.target_observation_version != 1 or raw is None:
            return ObservedTarget("not_provided")
        if (not actor.on_map or actor.health <= 0 or actor.in_limbo
                or actor.native_id is None
                or actor.object_type not in (1, 2, 6, 15)):
            return ObservedTarget("unobservable")
        actor_agent = self.identity.agent_id(actor.pointer)
        actor_tracked = (self.identity.tracked(actor_agent)
                         if actor_agent is not None else None)
        if (actor_tracked is None or actor_tracked.last_seen_frame != state.frame
                or actor_tracked.house != actor.house
                or actor_tracked.object_type != actor.object_type
                or actor_tracked.native_id != actor.native_id):
            return ObservedTarget("unobservable")
        if raw.status == 2:
            return ObservedTarget("none")
        if raw.status != 3:
            return ObservedTarget("unobservable")
        target = legal.get(raw.object_pointer)
        if target is None or target.object_type != raw.object_type:
            return ObservedTarget("unobservable")
        # The v1 DLL only emits foreign references under verified FogOfWar=No,
        # shroud and cloak/disguise gates. Recheck the client's legal set too.
        if target.house == actor.house and target.native_id != raw.native_id:
            return ObservedTarget("unobservable")
        agent = self.identity.agent_id(target.pointer)
        tracked = self.identity.tracked(agent) if agent is not None else None
        if (tracked is None or tracked.last_seen_frame != state.frame
                or tracked.pointer != target.pointer
                or tracked.object_type != target.object_type
                or tracked.house != target.house
                or (target.native_id is not None
                    and tracked.native_id != target.native_id)):
            return ObservedTarget("unobservable")
        return ObservedTarget("object", agent)

    # ------------------------------------------------------------ 可见性
    def is_visible(self, obj: GameObject) -> bool:
        """对象对 Agent 阵营是否可见。

        默认判据是所在格未被遮蔽。在 `spawn.ini` 置 `FogOfWar=No` 时，引擎只有
        「未探索」与「可见」两态，遮蔽标志即精确可见性，故按它过滤得到的正是
        人类玩家在同一配置下能看到的世界——不存在偷看。

        局限：`FogOfWar=Yes` 时引擎存在灰色的「已探索但当前不可见」层，而
        `Cell.visibility` 与 `shroud_state` 虽在 proto 中声明却从不填充，故无法
        区分二者。若要支持该配置，须由本层按各单位的视野半径自行计算——视野
        半径不在类型表中，需要另找来源。此函数即该扩展点。
        """
        if self.map_data is None:
            # 没有底图时宁可认为自己看不见，也不要给出未经迷雾过滤的世界
            return False
        cell_x, cell_y = obj.coordinates.cell
        return not self.map_data.shrouded(cell_x, cell_y)

    @staticmethod
    def _is_neutral(state, obj) -> bool:
        for house in state.houses:
            if house.pointer == obj.house:
                return house.is_neutral
        return True

    # ------------------------------------------------------------ 便捷查询
    def by_agent_id(self, agent_id, state: GameState | None = None):
        """按 Agent 侧 id 取当前对象；已消失返回 `None`。"""
        state = state or self.last_state
        pointer = self.identity.pointer_of(agent_id)
        return state.object(pointer) if state and pointer else None

    def visible_cells(self):
        """产出当前可见的格坐标。"""
        if self.map_data is None:
            return
        for cell_x, cell_y in self.map_data.iter_cells():
            if not self.map_data.shrouded(cell_x, cell_y):
                yield cell_x, cell_y

    def explored_ratio(self) -> float:
        """已探索格占全图的比例。"""
        if self.map_data is None or not self.map_data.cell_count:
            return 0.0
        column = self.map_data.columns.get("shrouded", ())
        explored = sum(1 for value in column if not value)
        return explored / len(column)
