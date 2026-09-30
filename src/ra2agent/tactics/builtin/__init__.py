"""内置技法。每条技法是一个模块，最后在这里汇总。"""
from .combat import TACTICS as COMBAT_TACTICS
from .construction import TACTICS as CONSTRUCTION_TACTICS
from .micro import TACTICS as MICRO_TACTICS
from .opening import TACTICS as OPENING_TACTICS
from .production import TACTICS as PRODUCTION_TACTICS
from .report import TACTICS as REPORT_TACTICS

#: 全部内置技法。
TACTICS = (OPENING_TACTICS + PRODUCTION_TACTICS + CONSTRUCTION_TACTICS
           + COMBAT_TACTICS + MICRO_TACTICS + REPORT_TACTICS)
