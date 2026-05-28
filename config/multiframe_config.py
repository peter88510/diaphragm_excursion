"""Multi-frame Excursion 模式 config（Step 10）。

三種 mode（互斥）：
  - LEGACY        : 傳統 per-frame loop。
                    legacy_frame_indices=None → 跑所有 frame；
                    legacy_frame_indices=[...]  → 只跑指定 indices（debug / 抽樣用）
  - GLOBAL_WINDOW : Mode 1 keyframe 拼接
  - REALTIME      : Mode 2 incremental — frame[0] 跳過（探頭啟動），frame[1..N] 各取右尾
                    stride_pixel append buffer，每幀 rolling excursion（累積 width = N × stride）；
                    每 realtime_wavelet_refresh_every_n 幀對整段 buffer 重做 wavelet 避免邊界 artifact 累積

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
    keyframe_indices: List[int] = field(default_factory=lambda: [86, 149])

    # GLOBAL_WINDOW / REALTIME 共用：每 frame 在 M-mode 影像上的位移
    stride_pixel: int = 8

    # GLOBAL_WINDOW first 段長度（pixel，從 frame[0] 左邊界往右取）
    # None = 自動算 min(keyframe_indices[0] × stride_pixel, frame_width)
    stitch_length_px_first: Optional[int] = None

    # GLOBAL_WINDOW second 段長度（pixel，從 frame[1] 右邊界往左取）
    # None = 自動算 (keyframe_indices[1] - keyframe_indices[0]) × stride_pixel
    stitch_length_px_second: Optional[int] = None

    # --- REALTIME ---
    # 純右尾累積：frame[0] 跳過（探頭啟動），frame[1..N] 各取右尾 stride_pixel；
    # 累積 width = N × stride_pixel

    # UX gating（viz 層用）：累積到此 frame 數前標 "warming up"，不疊 overlay
    realtime_warmup_frames: int = 0

    # Algorithm 安全網：累積 signal width < 此值跳過全局 brightness_way（避免 garbage）
    realtime_algorithm_min_width: int = 200

    # 每 k frame 對整段 buffer 重做 wavelet smoothing（消純右尾 concat 的邊界 artifact）
    # None = 不重做（純 append）
    realtime_wavelet_refresh_every_n: Optional[int] = 50

    # 跑到第幾幀停止；None = 跑完整 sequence（測試用）
    realtime_max_frames: Optional[int] = None
