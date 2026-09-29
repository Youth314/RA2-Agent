"""内置技法。每条技法是一个模块，最后在这里汇总。"""
from .micro import TACTICS as MICRO_TACTICS
from .opening import TACTICS as OPENING_TACTICS

#: 全部内置技法。
TACTICS = OPENING_TACTICS + MICRO_TACTICS
