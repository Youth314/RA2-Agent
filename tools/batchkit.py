#!/usr/bin/env python3
"""长批次测试的脚手架：占用焦点跑测试，结束时归还焦点并通知用户。

焦点被游戏占走期间用户看不到终端，因此每批结束时必须发通知，否则用户无法
得知批次已结束。

用法:
    from batchkit import focused_batch
    with focused_batch("甲组时序"):
        ...跑测试...
"""
import contextlib
import time

import notify
import winfocus


@contextlib.contextmanager
def focused_batch(name, restore=True):
    """把焦点交给游戏，退出时归还给进入前的窗口并发通知。

    无论批次内抛出与否都会归还焦点并发通知，避免把用户锁在游戏窗口外。
    """
    prev, prev_title = winfocus.foreground()
    began = time.time()
    winfocus.focus_game()
    error = None
    try:
        yield
    except BaseException as exc:      # noqa: BLE001 - 记录后原样抛出
        error = exc
        raise
    finally:
        elapsed = time.time() - began
        if restore and prev:
            winfocus.focus_handle(prev)
        if error is None:
            status, detail = "完成", f"耗时 {elapsed:.0f} 秒"
        else:
            status = "出错"
            detail = f"耗时 {elapsed:.0f} 秒，{type(error).__name__}: {error}"
        notify.notify(f"RA2 批次「{name}」{status}",
                      f"{detail}。焦点已归还，可以查看结果。")


def run(name, fn):
    """在占用焦点的批次里执行 fn。"""
    with focused_batch(name):
        return fn()
