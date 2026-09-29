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
    #: 投递超时（秒）。
    timeout: float = DEFAULT_TIMEOUT

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


def _post(endpoint, payload, timeout):
    """投一次 HTTP。返回 `(ok, 正文)`；网络问题归到 `(False, 原因)`。"""
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
        self._pending: list = []
        self._last_frame = None
        self._sent = 0
        #: 投递记录，供 `status` 报给模型。
        self.records: list = []
        self.max_records = 64

    # ------------------------------------------------------------ 对外
    def request(self, text, frame, tactic="", session="") -> dict:
        """请求唤醒模型。返回这一条的记录。

        被限流挡住时**不丢内容**——攒进待发队列，下次投递时并成一条。
        """
        text = (text or "").strip()
        record = {"frame": frame, "tactic": tactic, "text": text}
        if not text:
            record["skipped"] = "空说明"
            return self._keep(record)
        if self._sent >= self.policy.max_per_match:
            record["skipped"] = f"本局额度用尽（{self.policy.max_per_match} 次）"
            return self._keep(record)
        if self._too_soon(frame):
            self._pending.append(text)
            del self._pending[:-self.policy.max_pending]
            record["deferred"] = f"距上次不足 {self.policy.min_frames} 帧，已并入待发队列"
            return self._keep(record)

        payload = self._payload(text, frame, tactic, session)
        ok, body = self._post(self.endpoint, payload, self.timeout)
        record["sent"] = ok
        if ok:
            self._sent += 1
            self._last_frame = frame
            self._pending.clear()
            record["reply"] = _summarize(body)
        else:
            # 投不出去就留着，下次并进去重投——静默丢事件比报错糟得多
            self._pending.append(text)
            record["error"] = body
        return self._keep(record)

    @property
    def sent(self) -> int:
        """本局已投递几次。"""
        return self._sent

    @property
    def pending(self) -> tuple:
        """还没送出去的内容。"""
        return tuple(self._pending)

    # ------------------------------------------------------------ 内部
    def _too_soon(self, frame) -> bool:
        return (self._last_frame is not None
                and frame - self._last_frame < self.policy.min_frames)

    def _payload(self, text, frame, tactic, session) -> dict:
        """把待发的与这次的并成一条——一次唤醒就是一轮 LLM 调用，能省则省。"""
        combined = list(self._pending)
        if text not in combined:
            combined.append(text)
        return {"text": "\n".join(f"- {piece}" for piece in combined),
                "frame": frame, "tactic": tactic, "session": session,
                "merged": len(combined)}

    def _keep(self, record) -> dict:
        self.records.append(record)
        del self.records[:-self.max_records]
        if self.log is not None:
            self.log.record(record["frame"], "wake_requested",
                            detail={"issuer": "trigger:wake", **record})
        return record


def _summarize(body, limit=200) -> str:
    return (body or "").strip().replace("\n", " ")[:limit]
