"""本项目抛出的异常。

调用方按需捕获：`InvalidCommand` 表示命令在本地被拒，游戏未受影响；
`Timeout` 与 `GameNotResponding` 表示游戏侧没有回应。
"""


class Ra2Error(Exception):
    """本项目所有异常的基类。"""


class ProtocolError(Ra2Error):
    """与服务端的协议层错误。

    含握手失败、消息解析失败、以及服务端返回非零响应码。
    """


class ConnectionLost(ProtocolError):
    """与服务端的连接断了。

    `ProtocolError` 也用于协议内容不合法与状态查找失败，那时连接本身还是好的。
    只有本类表示这条连接不再可用，上层据此丢弃整条会话再重建。
    """


class InvalidCommand(Ra2Error, ValueError):
    """命令在本地被拒绝。

    继续发送会崩溃游戏或必然失败，因此在发送前抛出。规则见
    `.agents/notes/命令接口源码结论.md` 的前置校验清单。
    """


class GameNotResponding(Ra2Error):
    """游戏主循环未推进。

    RA2 单机在窗口失焦时暂停主循环，排队命令不会执行且帧号不增长。
    """


class Timeout(Ra2Error):
    """等待结果超时。"""


class CommandFailed(Ra2Error):
    """服务端执行命令后返回失败。

    `error_message` 为服务端原文；引擎拒绝的原因即在此，例如
    `object not found`、`invalid unit action`、`Proximity check failed`。

    `reason` 是归一化后的原因码（见 `executor.ERROR_REASONS`），供上层按稳定
    分支处理；原文措辞不一，只有 `reason` 适合入判断。
    """

    def __init__(self, message, command_type=None, reason="unknown"):
        super().__init__(message)
        self.command_type = command_type
        self.reason = reason


class TacticError(Ra2Error):
    """技法调用出错。"""


class TacticDenied(TacticError):
    """技法被拒绝。

    `kind` 区分两种：`policy` 是等级超出门槛或不在启用清单，`condition` 是适用
    条件不满足。前者任何情况下都不放行，后者允许被组合技法当作「这次不适用」。
    """

    def __init__(self, message, kind="policy"):
        super().__init__(message)
        self.kind = kind


class TacticFailed(TacticError):
    """技法自身抛了异常。异常隔离在此：一次调用作废，运行时继续。"""
