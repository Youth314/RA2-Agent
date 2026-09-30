#!/usr/bin/env python3
"""窗口置前的命令行入口；实现在 `ra2agent.deploy.winfocus`。

本文件保留，是因为操作手册与 `tools/batchkit.py` 都按这个名字引用它，而手册里的
命令写作 `python3 tools/winfocus.py reset`——没有 `PYTHONPATH`。故这里自己把仓库
的 `src` 放进 `sys.path`，那条命令照旧可用。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ra2agent.deploy.winfocus import (GAME_TITLE, find_window, focus_away,  # noqa: E402,F401
                               focus_game, focus_handle, focus_title,
                               foreground, is_game_foreground, list_windows,
                               main, reset)


if __name__ == "__main__":
    raise SystemExit(main())
