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

    **已展开的基地车在观测里是建筑**（建造厂），故也按建筑跳过：引擎对它再收一次
    `Deploy` 不会有任何变化，那条「等待变身」的判据永远不成立，任务就一直挂在
    「在管」占着那栋建造厂（实测：显式调用后基地被占死，对同单位下别的技法一律
    被拒「这些单位已在其它任务里」）。
    """
    wanted = {context.type_pointer(name) for name in CONSTRUCTION_VEHICLES}
    wanted.discard(None)
    if not wanted:
        return ()
    units = []
    for agent in context.subject.agents():
        found = context.subject.object_of(agent)
        if found is None or found.in_limbo or found.is_building:
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
        # 没有该展开的基地车就是「没事可做」：模型误对建造厂或别的单位调用时，
        # 任务当场收工交还单位，而不是挂成永久僵尸（实测挂过两千多帧）。
        idle_ends_task=True,
    ), _deploy_mcv),
)
