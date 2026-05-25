"""TargetSelection：根據 RunConfig.use_segment_label，從 detection_pass1 / refined
之間選定下游 excursion 演算法要用的 target_binary 與 diaphragm_mask。

取代原 patch_code 的 ImageStore 全域可變容器：
  - 不再以 mutable container 累積散落欄位
  - 結構化 dataclass，一次建構、不可變
  - 欄位名稱對應「下游用途」（target_binary / diaphragm_mask）而非「歷史成因」
    （overlay / temp / temp2）
"""
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

from algorithm.diaphragm_detection import DetectionResult
from algorithm.roi_band.enhanced_search import RoiSearchResult


@dataclass
class TargetSelection:
    target_binary: Optional[np.ndarray]   # 邊界計算用（連續線段）；找不到 target 時為 None
    diaphragm_mask: np.ndarray            # 橫膈膜 ROI mask（給下游 ROI 用）
    overlay: np.ndarray                   # debug viz，等於 refined.padded_overlay
    enhanced_padded: np.ndarray           # 強化後 padded 原圖大小，等於 refined.enhanced_padded
    source: str                           # 'segment' or 'classical'，debug 用


def select_target(
    detection_pass1: DetectionResult,
    refined: RoiSearchResult,
    y_band: Tuple[int, int],
    image_shape: Tuple[int, int],
    use_segment_label: bool,
) -> TargetSelection:
    """選擇下游 excursion 用的 target_binary 與 diaphragm_mask。

    Args:
        detection_pass1: 第一次 detect 的結果（吃 paddle seg mask）
        refined: enhanced_search 的結果（強化 + 第二次 detect）
        y_band: compute_target_y_range 算出的 (y_min, y_max)
        image_shape: (h, w) — 原圖大小，給 classical path 的 target_binary pad 用
        use_segment_label: True 用 paddle 結果；False 用古典強化結果
    """
    if use_segment_label:
        target_binary, diaphragm_mask = _select_from_segment(detection_pass1)
        source = 'segment'
    else:
        target_binary, diaphragm_mask = _select_from_classical(
            refined, y_band, image_shape)
        source = 'classical'

    return TargetSelection(
        target_binary=target_binary,
        diaphragm_mask=diaphragm_mask,
        overlay=refined.padded_overlay,
        enhanced_padded=refined.enhanced_padded,
        source=source,
    )


def _select_from_segment(
    detection_pass1: DetectionResult,
) -> Tuple[Optional[np.ndarray], np.ndarray]:
    """use_segment_label=True 路徑：用第一次 detect 的 paddle seg 結果。"""
    if detection_pass1.target_binary is None:
        return None, detection_pass1.filtered_binary
    return detection_pass1.target_binary, detection_pass1.target_binary


def _select_from_classical(
    refined: RoiSearchResult,
    y_band: Tuple[int, int],
    image_shape: Tuple[int, int],
) -> Tuple[Optional[np.ndarray], np.ndarray]:
    """use_segment_label=False 路徑：用第二次 detect (refined) 的結果。"""
    if refined.detection.target_binary is None:
        return None, refined.padded_mask

    # 第二次 detect 的 target_binary 在 band 內，需 pad 回原圖大小
    h, w = image_shape
    y_min, y_max = y_band
    target_padded = np.zeros((h, w), dtype=np.uint8)
    target_padded[y_min:y_max, :] = refined.detection.target_binary
    return target_padded, refined.padded_mask
