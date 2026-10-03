"""唤醒桥：把「该让模型来决定」的请求投给 DSH 侧的桥插件。

MCP 通道送不回来（DSH 的 mcp-client 只订阅工具列表变化，没有把服务端通知转给插件
的路），所以由 DSH 那边的一个插件在本地开一个 HTTP 路由，这里投过去，它再以 user
消息注入会话，把模型叫醒。

**一次唤醒就是一轮 LLM 调用**，是一局里的稀缺资源。故两道闸：

- **限流**：两次唤醒之间至少隔若干游戏帧；
- **合并**：被限流挡住的内容不丢，攒进待发队列，下次投递时并成一条。

失败会记进记录——**静默丢事件比报错糟得多**。
"""
import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field, fields

#: 桥插件的路由。它挂在 **DSH 的 WebServer 上**（与 GUI 同一个端口），不是自己另开
#: 一个——所以这里填的是 DSH 的地址。端口随部署变，故以 `config/wake.json` 为准。
DEFAULT_ENDPOINT = "http://127.0.0.1:3080/ra2/wake"

#: 投递超时（秒）。本地路由，不该久等。
DEFAULT_TIMEOUT = 3.0


@dataclass(frozen=True)
class WakePolicy:
    """唤醒的节制。可从 `config/wake.json` 读。"""

    #: 桥插件的路由。
    endpoint: str = DEFAULT_ENDPOINT
    #: 两次唤醒之间至少隔这么多**游戏帧**。按帧不按秒——失焦时帧不走。
    min_frames: int = 180
    #: 一局最多唤醒几次。写歪的策略不该烧掉一整局的额度。
    max_per_match: int = 30
    #: 一次投递里最多带几段合并进来的说明。
    max_pending: int = 8
    #: 待发项最多留多少帧（60 帧≈1 秒）。更久的直接丢：事件早结束了。
    stale_frames: int = 1800
    #: 投递超时（秒）。
    timeout: float = DEFAULT_TIMEOUT
    #: 唤醒投给哪个 DSH 会话。留空则交给桥插件按「唯一候选」去猜——一台机器上跑
    #: 两个玩家时会唤醒错人，故每个玩家的服务端都该显式给一个。
    session: str = ""

    @classmethod
    def load(cls, path) -> "WakePolicy":
        """从 JSON 文件读取；文件不存在时用默认值。认不出的键报错，不静默忽略。"""
        import pathlib
        source = pathlib.Path(path)
        if not source.exists():
            return cls()
        data = json.loads(source.read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"config/wake.json 里有认不出的键：{sorted(unknown)}")
        return cls(**data)


def _error_of(body):
    """插件回话里的 `error` 字段；读不出就给原文。

    回话是 JSON（中文可能被转义），直接塞进 `record["error"]` 会让人读到一坨
    `\\u4f1a\\u8bdd`。这里取出那句人话。
    """
    try:
        data = json.loads(body or "")
    except ValueError:
        return (body or "").strip()
    if isinstance(data, dict) and isinstance(data.get("error"), str):
        return data["error"]
    return (body or "").strip()


def _verdict(body):
    """从桥插件的回话里读 `ok` 字段。

    插件对「能解析但拒绝」的请求回的是 **HTTP 200 + `{"ok": false, "error": …}`**
    （会话不存在、持久化没确认都是这种）。故只看 HTTP 码会把这种失败当成功。
    不是 JSON 或没有 `ok` 字段时给 `None`——无从判断，就别替它下结论。
    """
    try:
        data = json.loads(body or "")
    except ValueError:
        return None
    if isinstance(data, dict) and "ok" in data:
        return bool(data["ok"])
    return None


def _post(endpoint, payload, timeout):
    """投一次 HTTP，返回 `(HTTP 成功?, 正文)`。网络问题归到 `(False, 原因)`。

    **判成败不在这里**：插件对「能解析但拒绝」的请求回 HTTP 200 + `{"ok": false}`，
    故由 `WakeBridge.request` 读回话里的 `ok`（见 `_verdict`）。
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return True, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        return False, f"HTTP {error.code}：{detail[:200]}"
    except (urllib.error.URLError, OSError, ValueError) as error:
        return False, str(error)


class WakeBridge:
    """把唤醒请求投给 DSH。限流、合并、记账都在这。"""

    def __init__(self, endpoint=None, policy=None, poster=None,
                 log=None, timeout=None):
        self.policy = policy or WakePolicy()
        # 显式给的端点优先，其次看配置，最后才是内置默认
        self.endpoint = endpoint or self.policy.endpoint
        self.timeout = timeout if timeout is not None else self.policy.timeout
        #: 投递函数，测试时换掉即可不碰网络。
        self._post = poster or _post
        self.log = log
        #: 待发队列保留原始记录及可选的建筑 Agent ID。带帧号是为了丢掉过期项——
        #: 但攒到事件早结束（实测一条帧 29750 的「建筑完工待放置」投到 55660 才到）就是
        #: 白花模型一轮：它醒来只会看到「这事早完了」。
        self._pending: list = []
        self._ready_buildings: frozenset | None = None
        self._last_frame = None
        self._sent = 0
        #: 投递记录，供 `status` 报给模型。
        self.records: list = []
        self.max_records = 64

    # ------------------------------------------------------------ 对外
    def update(self, observation, identity=None) -> None:
        """用已有合法观测清理待发项；不读取引擎，不触发 HTTP 重试。"""
        state = observation.state
        self._ready_buildings = None
        if state is not None and identity is not None:
            agents = [identity.agent_id(factory.object)
                      for factory in state.ready_building_factories()]
            if all(agent is not None for agent in agents):
                self._ready_buildings = frozenset(agents)
        self._prune(observation.frame)

    def request(self, text, frame, tactic="", session="", *,
                placement_building=None) -> dict:
        """请求唤醒模型。返回这一条的记录。

        被限流挡住时**不丢内容**——攒进待发队列，下次投递时并成一条。`session`
        留空时用策略里配好的那个；两边都空才让桥插件按唯一候选去猜。
        """
        return self.request_many(((text, placement_building),), frame,
                                 tactic=tactic, session=session)[0]

    def request_many(self, messages, frame, tactic="", session="") -> tuple:
        """同批说明分别留存关联依据，合并投递一次；不增加主动重试。"""
        session = session or self.policy.session
        self._prune(frame)
        records, active = [], []
        for text, agent in messages:
            record = {"frame": frame, "tactic": tactic, "text": (text or "").strip()}
            if agent is not None:
                record["placement_building"] = agent
            records.append(record)
            if not record["text"]:
                record["skipped"] = "空说明"
            elif self._placement_expired(record):
                record["expired"] = "关联建筑已不再待放置"
            else:
                active.append(record)
        if active:
            if self._sent >= self.policy.max_per_match:
                for record in active:
                    record["skipped"] = f"本局额度用尽（{self.policy.max_per_match} 次）"
            elif self._too_soon(frame):
                for record in active:
                    record["deferred"] = f"距上次不足 {self.policy.min_frames} 帧，已并入待发队列"
                    self._queue(record)
            else:
                payload = self._payload([record["text"] for record in active],
                                        frame, tactic, session)
                ok, body = self._post(self.endpoint, payload, self.timeout)
                # HTTP 200 + ok:false 仍是失败，不能清空待发说明。
                if ok and _verdict(body) is False:
                    ok = False
                if ok:
                    self._sent += 1
                    self._last_frame = frame
                    self._pending.clear()
                for record in active:
                    record["sent"] = ok
                    if ok:
                        record["reply"] = _summarize(body)
                    else:
                        record["error"] = _error_of(body)
                        self._pending.append(record)
        return tuple(self._keep(record, event=("wake_expired" if record.get("expired")
                                              else "wake_requested"))
                     for record in records)

    @property
    def sent(self) -> int:
        """本局已投递几次。"""
        return self._sent

    @property
    def pending(self) -> tuple:
        """还没送出去的内容（不含已过期的，见 `_prune`）。"""
        return tuple(record["text"] for record in self._pending)

    # ------------------------------------------------------------ 内部
    def _too_soon(self, frame) -> bool:
        return (self._last_frame is not None
                and frame - self._last_frame < self.policy.min_frames)

    def _prune(self, frame) -> int:
        """丢掉过期太久的待发项，返回丢了几条。

        按现有时间上限及关联建筑是否仍待放置判断；观测不足时只用时间上限。
        """
        keep, dropped = [], 0
        for record in self._pending:
            reason = ("超过通知有效期" if frame - record["frame"] > self.policy.stale_frames
                      else "关联建筑已不再待放置" if self._placement_expired(record) else "")
            if not reason:
                keep.append(record)
                continue
            record["expired"] = reason
            dropped += 1
            self._keep({"frame": frame, "tactic": record["tactic"],
                        "text": record["text"], "origin_frame": record["frame"],
                        "expired": reason}, event="wake_expired")
        self._pending = keep
        return dropped

    def _placement_expired(self, record):
        agent = record.get("placement_building")
        return (agent is not None and self._ready_buildings is not None
                and agent not in self._ready_buildings)

    def _queue(self, record):
        self._pending.append(record)
        del self._pending[:-self.policy.max_pending]

    def _payload(self, texts, frame, tactic, session) -> dict:
        """把待发的与这次的并成一条——一次唤醒就是一轮 LLM 调用，能省则省。"""
        self._prune(frame)
        combined = list(dict.fromkeys(record["text"] for record in self._pending))
        combined = list(dict.fromkeys(combined + list(texts)))
        # 说明本身可能是多行（事件列表已自带 `- `）：逐行再加前缀会出 `- -`，空条目
        # 也会变成光秃秃一个 `- `（实测玩家收到过 `- -` 与空条目）。故按整段拼，段间
        # 空一行，并滤掉空段。
        pieces = [piece.strip() for piece in combined if piece and piece.strip()]
        return {"text": "\n\n".join(pieces),
                "frame": frame, "tactic": tactic, "session": session,
                "merged": len(combined)}

    def _keep(self, record, *, event="wake_requested") -> dict:
        self.records.append(record)
        del self.records[:-self.max_records]
        if self.log is not None:
            self.log.record(record["frame"], event,
                            detail={"issuer": "trigger:wake", **record})
        return record


def _summarize(body, limit=200) -> str:
    return (body or "").strip().replace("\n", " ")[:limit]
