"""Multi-frame Excursion（Step 10）。

11A：frame_selection helpers
11B：global_window 拼接 + 全局 excursion
11C-LEGACY / 11C-GW：main.py 整合 LEGACY / GLOBAL_WINDOW
14A：realtime incremental buffer + rolling excursion（RealtimeState；main 驅動 loop）
"""
from algorithm.multiframe.frame_selection import (
    get_keyframe_indices,
    get_legacy_frame_indices,
)
from algorithm.multiframe.global_window import (
    GlobalExcursionResult,
    run_global_window,
)
from algorithm.multiframe.realtime import RealtimeState

__all__ = [
    "get_legacy_frame_indices",
    "get_keyframe_indices",
    "run_global_window",
    "GlobalExcursionResult",
    "RealtimeState",
]
