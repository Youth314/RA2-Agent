"""Attack v1 单次请求；尚未取得真机效果证据。"""
from ra2agent.runtime.intents import AttackTarget
from ra2agent.tactics.core import REQUIRED, Param, Tactic, TacticInfo, is_positive_int


def run(ctx):
    return (ctx.intent(AttackTarget, units=ctx.subject.agents(), target=ctx.params["target"]),)


TACTICS = (Tactic(TacticInfo(
    name="attack_target",
    summary="实验 Attack v1：单个己方车辆点名合法敌方车辆或建筑；新攻击输入与实际目标匹配后释放租约，"
            "不承诺开火、击毁或持续控制；真机未验",
    params=(Param("target", REQUIRED, "敌方目标 Agent ID", is_positive_int),),
    requires=("has_units", "has_map", "attack_v1"),
), run),)
