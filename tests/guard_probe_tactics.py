"""仅供隔离测试注册表使用的确定性技法；不注册进正式目录。"""
from ra2agent.runtime.intents import GuardCurrent, GuardPosition


def guard_current(ctx):
    return (ctx.intent(GuardCurrent, units=ctx.subject.agents()),)


def guard_position(ctx):
    return (ctx.intent(GuardPosition, units=ctx.subject.agents(),
                       cell=tuple(ctx.params["cell"])),)
