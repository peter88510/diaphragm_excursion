"""Multi-frame Excursion（Step 10）。

11A：frame_selection helpers
11B：global_window 拼接 + 全局 excursion
11C-LEGACY：main.py 整合 LEGACY mode（已完成）
11C-GW：main.py 整合 GLOBAL_WINDOW mode（待）
"""
from algorithm.multiframe.frame_selection import (
    get_keyframe_indices,
    get_legacy_frame_indices,
)
from algorithm.multiframe.global_window import (
    GlobalExcursionResult,
    run_global_window,
)

__all__ = [
    "get_legacy_frame_indices",
    "get_keyframe_indices",
    "run_global_window",
    "GlobalExcursionResult",
]
