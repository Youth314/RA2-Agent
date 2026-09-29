"""开局类技法：不需要模型在场就该发生的事。

与 `micro.py` 的区别是这些**自己会跑**——名片里带 `trigger`。它们产出的是脉冲：
跑一次、下发一次、不建编队，故不会占着单位的租约，也不会有每拍重发的风险。
"""
from ...intents import Deploy
from ..core import Tactic, TacticInfo, Trigger

#: 基地车的注册名。显示名是「Construction Vehicle」，不含 MCV，故按注册名认。
CONSTRUCTION_VEHICLES = ("AMCV", "SMCV", "PCV")

#: 多久看一次有没有该展开的基地车。按游戏帧，失焦时帧不走。
CHECK_EVERY_FRAMES = 30


def _deploy_mcv(context):
    """把还没展开的基地车就地展开。

    已经在展开或已收起的跳过——不给这两项，会对正在展开的基地车重复下令。
    """
    wanted = {context.type_pointer(name) for name in CONSTRUCTION_VEHICLES}
    wanted.discard(None)
    if not wanted:
        return ()
    units = []
    for agent in context.subject.agents():
        found = context.subject.object_of(agent)
        if found is None or found.in_limbo:
            continue
        if found.type_pointer not in wanted or found.deployed or found.deploying:
            continue
        units.append(agent)
    if not units:
        return ()
    return (context.intent(Deploy, units=tuple(units)),)


TACTICS = (
    Tactic(TacticInfo(
        name="deploy_mcv",
        summary="把还没展开的基地车就地展开；开局自己跑，不必等模型下令",
        requires=("has_units",),
        trigger=Trigger.every(CHECK_EVERY_FRAMES),
    ), _deploy_mcv),
)
