"""Multi-frame Excursion（Step 10）。

11A：frame_selection helpers
11B：global_window 拼接 + 全局 excursion（未完成）
"""
from algorithm.multiframe.frame_selection import (
    get_keyframe_indices,
    get_legacy_frame_indices,
)

__all__ = ["get_legacy_frame_indices", "get_keyframe_indices"]
