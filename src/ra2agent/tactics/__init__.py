"""技法库。

L0 只做基础设施，其上的能力由模型自己写成技法，按需组合。形态、接口与门控见
`.agents/notes/技法框架.md`；写技法的规范见
`.agents/skills/ra2-write-tactic/SKILL.md`。

用法：

```python
registry = TacticRegistry(TacticPolicy.load("config/tactics.json")).load_builtin()
for card in registry.cards(Mode.MATCH, observation, squad):
    print(card.text())
```
"""
from .conditions import CONDITIONS, condition
from .core import (LEVEL_ORDER, REQUIRED, Card, Level, Mode, Param, Tactic,
                   TacticContext, TacticInfo, TacticPolicy, TacticRegistry)

__all__ = [
    "Card", "Level", "LEVEL_ORDER", "Mode", "Param", "REQUIRED", "Tactic",
    "TacticContext", "TacticInfo", "TacticPolicy", "TacticRegistry",
    "CONDITIONS", "condition",
]
