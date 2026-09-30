"""Agent 侧的对象标识。

引擎的 `pointer_self` 不能作长期标识：基地车部署成建造厂时，原对象被销毁、
另建一个建筑对象，指针随之改变（实测见
`.agents/notes/命令能力测绘结果.md#对象指针的稳定性`）。

本模块为每个对象分配一个 Agent 侧 id，并在每次观测时重新解析。对象发生变身
时 id **延续不变**，使指向它的意图不会因变身而失联。
"""
from dataclasses import dataclass, field

#: 变身配对允许的格距离。基地车部署后的建造厂会略有偏移，实测约 3 格。
DEFAULT_MATCH_RADIUS = 6
#: 对象缺席多少帧后才判定为消失。留出宽限期以覆盖变身跨帧的情况。
DEFAULT_GRACE_FRAMES = 45


@dataclass
class TrackedObject:
    """一个被跟踪的对象。"""

    agent_id: int
    pointer: int
    first_seen_frame: int
    last_seen_frame: int
    house: int
    object_type: int
    type_pointer: int
    cell: tuple[int, int]
    #: 变身前的引擎指针；未发生变身时为 `None`。agent id 在变身时延续不变。
    previous_pointer: int | None = None

    def __repr__(self):
        return (f"TrackedObject(agent_id={self.agent_id}, pointer={self.pointer},"
                f" type={self.object_type}, cell={self.cell},"
                f" previous_pointer={self.previous_pointer})")


@dataclass
class IdentityDelta:
    """一次观测相对上一次的变化。"""

    frame: int
    #: 新出现的对象的 agent id。
    appeared: list = field(default_factory=list)
    #: 确认消失的 agent id。
    vanished: list = field(default_factory=list)
    #: 发生变身的 `(agent_id, 新指针)`。
    transformed: list = field(default_factory=list)

    @property
    def empty(self) -> bool:
        """本次观测有无变化。"""
        return not (self.appeared or self.vanished or self.transformed)


class IdentityTable:
    """维护 Agent 侧 id 与引擎指针的对应关系。

    每次观测后调用 `update`。同一个对象只要没消失，其 agent id 就保持不变，
    即使引擎指针变了。
    """

    def __init__(self, match_radius=DEFAULT_MATCH_RADIUS,
                 grace_frames=DEFAULT_GRACE_FRAMES):
        self.match_radius = match_radius
        self.grace_frames = grace_frames
        self._tracked: dict[int, TrackedObject] = {}
        self._by_pointer: dict[int, int] = {}
        self._next_id = 1

    # ------------------------------------------------------------ 查询
    def agent_id(self, pointer) -> int | None:
        """引擎指针对应的 agent id；未知返回 `None`。"""
        return self._by_pointer.get(_pointer_of(pointer))

    def pointer_of(self, agent_id) -> int | None:
        """agent id 当前的引擎指针；已消失返回 `None`。"""
        tracked = self._tracked.get(_id_of(agent_id))
        return tracked.pointer if tracked else None

    def tracked(self, agent_id) -> TrackedObject | None:
        """按 agent id 取跟踪记录。"""
        return self._tracked.get(_id_of(agent_id))

    def known(self) -> set:
        """当前全部 agent id。"""
        return set(self._tracked)

    def pointers(self) -> set:
        """当前全部引擎指针。"""
        return set(self._by_pointer)

    def __len__(self):
        return len(self._tracked)

    # ------------------------------------------------------------ 更新
    def update(self, state) -> IdentityDelta:
        """用一帧观测推进标识表，返回本次的变化。"""
        frame = state.frame
        observed = {o.pointer: o for o in state.objects}
        delta = IdentityDelta(frame=frame)

        newcomers = [p for p in observed if p not in self._by_pointer]
        absent = [p for p in self._by_pointer if p not in observed]

        for pointer, obj in observed.items():
            agent = self._by_pointer.get(pointer)
            if agent is not None:
                self._refresh(self._tracked[agent], obj, frame)

        for pointer in newcomers:
            obj = observed[pointer]
            partner = self._claim_transformation(obj, absent, frame)
            if partner is None:
                delta.appeared.append(self._create(obj, frame))
            else:
                absent.remove(partner)
                agent = self._by_pointer[partner]
                self._retarget(agent, obj, frame)
                delta.transformed.append((agent, pointer))

        for pointer in absent:
            agent = self._by_pointer[pointer]
            if frame - self._tracked[agent].last_seen_frame >= self.grace_frames:
                self._forget(agent)
                delta.vanished.append(agent)

        return delta

    # ------------------------------------------------------------ 内部
    def _create(self, obj, frame) -> int:
        agent = self._next_id
        self._next_id += 1
        self._tracked[agent] = TrackedObject(
            agent_id=agent, pointer=obj.pointer, first_seen_frame=frame,
            last_seen_frame=frame, house=obj.house, object_type=obj.object_type,
            type_pointer=obj.type_pointer, cell=obj.coordinates.cell)
        self._by_pointer[obj.pointer] = agent
        return agent

    def _refresh(self, tracked, obj, frame):
        tracked.last_seen_frame = frame
        tracked.type_pointer = obj.type_pointer
        tracked.object_type = obj.object_type
        tracked.cell = obj.coordinates.cell

    def _retarget(self, agent, obj, frame):
        """把现有 agent id 指向新指针，并记下变身前的指针。"""
        tracked = self._tracked[agent]
        self._by_pointer.pop(tracked.pointer, None)
        tracked.previous_pointer = tracked.pointer
        tracked.pointer = obj.pointer
        self._by_pointer[obj.pointer] = agent
        self._refresh(tracked, obj, frame)

    def _forget(self, agent):
        tracked = self._tracked.pop(agent)
        self._by_pointer.pop(tracked.pointer, None)

    def _claim_transformation(self, obj, absent, frame):
        """在刚缺席的对象里找一个可能是本对象前身的。

        条件：同一阵营、类型种类发生变化、位置在半径内、缺席未超过宽限期。
        同种类不算变身，避免把「一辆坦克被毁、旁边新造一辆」误判成变身。
        """
        best, best_distance = None, None
        for pointer in absent:
            previous = self._tracked[self._by_pointer[pointer]]
            if previous.house != obj.house:
                continue
            if frame - previous.last_seen_frame > self.grace_frames:
                continue
            if previous.object_type == obj.object_type:
                continue
            cell = obj.coordinates.cell
            dx = previous.cell[0] - cell[0]
            dy = previous.cell[1] - cell[1]
            distance = dx * dx + dy * dy
            if distance > self.match_radius ** 2:
                continue
            if best_distance is None or distance < best_distance:
                best, best_distance = pointer, distance
        return best


def _pointer_of(obj) -> int:
    return obj.pointer if hasattr(obj, "pointer") else int(obj)


def _id_of(agent) -> int:
    return agent.agent_id if isinstance(agent, TrackedObject) else int(agent)
