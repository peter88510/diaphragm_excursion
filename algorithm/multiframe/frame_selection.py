"""Frame / keyframe indices 取得（按 MultiframeMode / KeyframeStrategy）。

LEGACY mode → get_legacy_frame_indices()
GLOBAL_WINDOW mode → get_keyframe_indices() → 依 strategy dispatch
"""
from typing import List

from config.multiframe_config import (
    KeyframeStrategy,
    MultiframeConfig,
)
from input.frame_sequence import FrameSequence


def get_legacy_frame_indices(
    cfg: MultiframeConfig,
    seq: FrameSequence,
) -> List[int]:
    """LEGACY mode 要跑的 frame indices（0-indexed）。"""
    if cfg.legacy_frame_indices is None:
        return list(range(len(seq.frames)))
    return list(cfg.legacy_frame_indices)


def get_keyframe_indices(
    cfg: MultiframeConfig,
    seq: FrameSequence,
) -> List[int]:
    """GLOBAL_WINDOW mode 抽 keyframe（0-indexed）。"""
    if cfg.keyframe_strategy == KeyframeStrategy.FIXED_INDICES:
        return list(cfg.keyframe_indices)
    if cfg.keyframe_strategy == KeyframeStrategy.PHASE_CORRELATE:
        return _phase_correlate_keyframes(seq, cfg)
    raise ValueError(f"Unknown keyframe_strategy: {cfg.keyframe_strategy}")


def _phase_correlate_keyframes(
    seq: FrameSequence,
    cfg: MultiframeConfig,
) -> List[int]:
    """透過 phase correlate 累加每 frame 位移，輸出 keyframe indices。

    待 user 補上實作（目前用 FIXED_INDICES 走過 11B）。
    """
    raise NotImplementedError(
        "Phase correlate keyframe extraction 待實作；"
        "請用 KeyframeStrategy.FIXED_INDICES 或補上本函式"
    )
