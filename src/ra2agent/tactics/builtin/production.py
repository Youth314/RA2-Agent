"""生产类技法：把 `Produce` 意图接出来。

两句实话写在最前面，都是框架现状决定的，不是设计选择：

1. **每次 `call` 都必须点名单位**（`Commander._check_units` 拒绝空单位），而生产是
   阵营级动作、不针对任何对象。故调用时用 `units` 点名**哪个厂来造**，意图也带上
   这些 id：运行时据此把「命令生效即到位」记在它们头上，任务当拍结算、单位随即
   交还，不会长期占着。这是框架限制，不是设计意图。
2. **买不买得起交给 `can_afford`**，不在技法里判。参数型条件现在真的会判（受理与
   运行时各判一次）；但它**不会让卡片消失**——`tactics` 工具不带参数，筛卡片时这类
   条件拿不到东西可判。

重复下单由技法自己挡：同类已在生产队列里就报错。任务当场失败并结算，`status` 的
「新结果」会带上这句原因，模型据此知道别重复下单。
"""
from ...errors import TacticError
from ...intents import Produce
from ..core import (REQUIRED, Param, Tactic, TacticInfo, is_non_empty_str)


def _already_queued(context, pointer):
    """这个类型是否已经排在某个生产队列里。"""
    state = context.observation.state
    if state is None:
        return False
    return any(pointer in tuple(factory.queued_objects)
               for factory in state.own_factories())


def _produce(context):
    """解析类型 → 查重 → 产出 `Produce`。

    认不出的类型与买不起的都由 `can_afford` 在受理时挡掉，故这里只剩「类型表还没
    取到」这一种该放弃的情况——按 skill 的要求，宁可这一拍什么都不做，也不拿个
    假指针去下单。
    """
    name = context.params["type"]
    pointer = context.type_pointer(name)
    if pointer is None:
        return ()
    if _already_queued(context, pointer):
        raise TacticError(f"{name} 已经在生产队列里，不要重复下单")
    return (context.intent(Produce, type_pointer=pointer, type_name=name),)


TACTICS = (
    Tactic(TacticInfo(
        name="train_unit",
        summary="让某个厂开始生产一种单位；units 点名哪个厂，params.type 用注册名",
        params=(Param("type", REQUIRED, "单位的注册名或显示名，如 MTNK",
                      is_non_empty_str),),
        requires=("can_afford", "prereq_met"),
    ), _produce),

    Tactic(TacticInfo(
        name="build_structure",
        summary="让建造厂开始生产一栋建筑；造好后还要 place_ready_building 放下",
        params=(Param("type", REQUIRED, "建筑的注册名或显示名，如 GAPOWR",
                      is_non_empty_str),),
        # `type_not_pending` 挡同型重复下单：原版对建筑不允许同型排队，第二次下单
        # 会被引擎悄悄吞掉（实测第二座矿厂走到 37/54 后无声消失）。
        requires=("can_afford", "has_construction_yard", "prereq_met",
                  "type_not_pending"),
    ), _produce),
)
