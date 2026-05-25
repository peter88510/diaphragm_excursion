"""Multi-frame Excursion 模式 config（Step 10）。

三種 mode（互斥）：
  - LEGACY        : 傳統 per-frame loop。default。
                    legacy_frame_indices=None → 跑所有 frame；
                    legacy_frame_indices=[...]  → 只跑指定 indices（debug / 抽樣用）
  - GLOBAL_WINDOW : Mode 1 keyframe 拼接（11B 落地）
  - REALTIME      : Mode 2 incremental（探索階段，11B+ 才考慮）

keyframe 取得策略（GLOBAL_WINDOW 用）：
  - FIXED_INDICES   : 直接照 cfg.keyframe_indices（experiment 預設 [88, 149]）。default。
                       時間效能優；犧牲拼接精度
  - PHASE_CORRELATE : 由 phase correlate 累加位移算出 keyframe（精度優；待 user 補實作）
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class MultiframeMode(Enum):
    LEGACY = 'legacy'
    GLOBAL_WINDOW = 'global_window'
    REALTIME = 'realtime'


class KeyframeStrategy(Enum):
    FIXED_INDICES = 'fixed_indices'
    PHASE_CORRELATE = 'phase_correlate'


@dataclass
class MultiframeConfig:
    mode: MultiframeMode = MultiframeMode.LEGACY

    # --- LEGACY ---
    # None = 跑所有 frame（同舊 main.py 行為）；list = 只跑指定 indices
    legacy_frame_indices: Optional[List[int]] = None

    # --- GLOBAL_WINDOW ---
    keyframe_strategy: KeyframeStrategy = KeyframeStrategy.FIXED_INDICES
    # FIXED_INDICES 時使用（0-indexed）；PHASE_CORRELATE 時 ignored
    keyframe_indices: List[int] = field(default_factory=lambda: [88, 149])

    # GLOBAL_WINDOW / REALTIME 共用：每 frame 在 M-mode 影像上的位移
    stride_pixel: int = 8
