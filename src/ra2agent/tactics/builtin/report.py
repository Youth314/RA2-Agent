"""告警类技法：出了事就把模型叫回来看一眼。

与 `opening.py` 的自动层技法不同，这条**不是替模型做事**，而是**请求它来判断**：
电力崩了是先补电还是先推、丢了单位要不要收缩、被人渗透了要不要查——这些只有
模型能决定。

一次唤醒就是一轮 LLM 调用，故节制不在技法里：限流、合并、额度都在
`ra2agent.wake.WakeBridge`（`config/wake.json`：一局最多 30 次、两次至少隔 180 帧，
被挡下的内容攒着下次并成一条投出去）。技法这一层只负责「确实出事了」这个判断。
"""
from ...engine.events import summarize
from ...runtime.intents import Wake
from ..core import Tactic, TacticInfo, Trigger

#: 值得把模型叫回来的事。**常规失败原因不在此列**——那是每拍都算得出来的事实，
#: 由 `status` 报，不该烧掉一局只有 30 次的唤醒额度。
WATCHED = ("low_power", "object_lost", "infiltrated", "player_defeated",
           "placement_ready")

#: 建筑完工时随唤醒附上的一句：放哪儿是模型的判断，别让它自己去猜坐标。
PLACEMENT_HINT = ("（放哪儿看 status 的「待放置」段：那里按方位给了可选落点；"
                  "也可以 call place_ready_building 不给 cell，由 L0 问引擎要一格）")


def watched_only(events):
    """从一批事件里挑出值得把模型叫回来的那些。

    技法与常驻监听（`ra2agent.watch`）共用这一份判据——两处各写一份迟早会漂。
    """
    out = []
    for event in events or ():
        if _kind_of(event) in WATCHED:
            out.append(event)
    return tuple(out)


def _report_trouble(context):
    """有事就唤醒模型，附上事件原文；没事返回空（空转不报给模型）。"""
    happened = watched_only(context.events)
    if not happened:
        return ()
    text = summarize(happened)
    if not text:
        return ()
    if any(_kind_of(event) == "placement_ready" for event in happened):
        text += "\n" + PLACEMENT_HINT
    return (context.intent(Wake, text=text),)


def _kind_of(event) -> str:
    """事件类型名。`EventKind` 是 `str` 枚举，但字符串也认。"""
    kind = getattr(event, "kind", event)
    return str(getattr(kind, "value", kind))


TACTICS = (
    Tactic(TacticInfo(
        name="report_trouble",
        summary="出事（掉单位、断电、被渗透、出局）时把模型叫回来看一眼",
        # 由事件驱动，不占单位、也不供模型直接调用：它做的事是「通知」，没有
        # 可下的命令，模型手动调一次只会得到空转。
        requires=(),
        expose=False,
        trigger=Trigger.on(*WATCHED),
    ), _report_trouble),
)
