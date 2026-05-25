"""Multi-frame Excursion 模式 config（Step 10）。

三種 mode（互斥）：
  - LEGACY        : 傳統 per-frame loop。default。
                    legacy_frame_indices=None → 跑所有 frame；
                    legacy_frame_indices=[...]  → 只跑指定 indices（debug / 抽樣用）
  - GLOBAL_WINDOW : Mode 1 keyframe 拼接
  - REALTIME      : Mode 2 incremental（探索階段）

keyframe 取得策略（GLOBAL_WINDOW 用）：
  - FIXED_INDICES   : 直接照 cfg.keyframe_indices（experiment 值，會隨資料調整）。default。
                       時間效能優；犧牲拼接精度
  - PHASE_CORRELATE : 由 phase correlate 累加位移算出 keyframe（精度優；待 user 補實作）

拼接視窗 pixel 邏輯（GLOBAL_WINDOW）：
  - first  段長度 = min(keyframe_indices[0] × stride_pixel, frame_width)
  - second 段長度 = (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel
  - 公式為 multi-frame 實驗結果；理論上 multi-frame 不會超過 2 keyframe
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
    mode: MultiframeMode = MultiframeMode.GLOBAL_WINDOW

    # --- LEGACY ---
    # None = 跑所有 frame（同舊 main.py 行為）；list = 只跑指定 indices
    legacy_frame_indices: Optional[List[int]] = None

    # --- GLOBAL_WINDOW ---
    keyframe_strategy: KeyframeStrategy = KeyframeStrategy.FIXED_INDICES
    # FIXED_INDICES 時使用（0-indexed）；PHASE_CORRELATE 時 ignored
    # 嚴格 2 個 keyframe（multi-frame 預期上限）；具體 default 隨 experiment 調整
    keyframe_indices: List[int] = field(default_factory=lambda: [87, 149])

    # GLOBAL_WINDOW / REALTIME 共用：每 frame 在 M-mode 影像上的位移
    stride_pixel: int = 8

    # GLOBAL_WINDOW first 段長度（pixel，從 frame[0] 左邊界往右取）
    # None = 自動算 min(keyframe_indices[0] × stride_pixel, frame_width)
    stitch_length_px_first: Optional[int] = None

    # GLOBAL_WINDOW second 段長度（pixel，從 frame[1] 右邊界往左取）
    # None = 自動算 (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel
    stitch_length_px_second: Optional[int] = None
