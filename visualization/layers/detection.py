"""Detection pass1 三張 debug 圖：debug_overlay / filtered / potential。

對應原 detector.py 內 `if config.visual: cv2.imshow×3`，現在每張各自落檔。
potential_binary 在 fallback 路徑會是 None — 此時跳過該張。

Detection pass2（enhanced_search 第二次 detect）的 overlay 也走本檔，
由 caller 傳 `RoiSearchResult.padded_overlay` 進來，避免反向 import roi_band。
"""
import numpy as np

from algorithm.diaphragm_detection import DetectionResult
from config.visualization_config import VisualizationConfig
from visualization import stages
from visualization.io import debug_path, save_png, should_save_debug


def render_detection_pass1(
    detection: DetectionResult,
    cfg: VisualizationConfig,
    frame_idx: int,
) -> None:
    """存 detection pass1 的三張中間圖。"""
    if should_save_debug(cfg, stages.DETECTION_PASS1_OVERLAY):
        save_png(
            detection.debug_overlay,
            debug_path(cfg, stages.DETECTION_PASS1_OVERLAY, frame_idx),
        )
    if should_save_debug(cfg, stages.DETECTION_PASS1_FILTERED):
        save_png(
            detection.filtered_binary,
            debug_path(cfg, stages.DETECTION_PASS1_FILTERED, frame_idx),
        )
    if (
        detection.potential_binary is not None
        and should_save_debug(cfg, stages.DETECTION_PASS1_POTENTIAL)
    ):
        save_png(
            detection.potential_binary,
            debug_path(cfg, stages.DETECTION_PASS1_POTENTIAL, frame_idx),
        )


def render_detection_pass2(
    overlay: np.ndarray,
    cfg: VisualizationConfig,
    frame_idx: int,
) -> None:
    """存 enhanced_search 第二次 detect 的 padded_overlay。"""
    if not should_save_debug(cfg, stages.DETECTION_PASS2_OVERLAY):
        return
    save_png(overlay, debug_path(cfg, stages.DETECTION_PASS2_OVERLAY, frame_idx))
