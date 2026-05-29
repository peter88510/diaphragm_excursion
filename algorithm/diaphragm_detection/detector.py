"""Diaphragm detection 主入口。

組合 classical / candidate / curve_fit 三件零件，從 gray image (+ optional
segmentation mask) 找出橫膈膜的 ROI、target binary 與 potential binary，
回傳統一的 DetectionResult。

對外只暴露 detect()，DetectionResult 也從此檔暴露給 algorithm package。

直接搬自 patch_code.py 的 detect_diaphragm，差別：
  - 拆出 classical / candidate / curve_fit 三件已 patch 過的子模組
  - 統一回傳 DetectionResult dataclass，不再依 phase 改變 5-tuple 內容語意
  - 所有參數從 DiaphragmDetectionConfig 注入
  - 移除 `file` 參數（原本 unused，作者註解亦標註）
  - 移除 `new_best_region` dead var
  - 移除 `len(potential_regions) >= 1` 與單一元素時的註解掉分支邏輯
"""
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from algorithm.diaphragm_detection.candidate import find_candidates
from algorithm.diaphragm_detection.classical import algo_segmentation
from algorithm.diaphragm_detection.curve_fit import diaphragm_curve_fit
from config.diaphragm_detection_config import DiaphragmDetectionConfig, Phase


@dataclass
class DetectionResult:
    """detect() 的輸出。所有 phase 用同一結構，caller 不必依 phase 解包。"""
    best_region: Tuple[int, int]                       # (y_top, y_bottom)
    filtered_binary: np.ndarray                        # 所有 connected components union
    target_binary: Optional[np.ndarray] = None         # 要丟給下游 excursion 算的 binary
    potential_binary: Optional[np.ndarray] = None      # potential candidates union
    debug_overlay: Optional[np.ndarray] = None         # color-coded viz（原 temp）


# 與原版一致的 fallback 染色順序
_OVERLAY_COLORS = [(0, 255, 255), (0, 255, 0), (255, 255, 0), (255, 0, 255)]
_COLOR_POTENTIAL = (0, 0, 255)
_COLOR_BEST = (255, 0, 0)


def detect(
    image: np.ndarray,
    config: DiaphragmDetectionConfig,
    use_segment: Optional[np.ndarray] = None,
    timing=None,
) -> DetectionResult:
    """從 gray image (+ optional segmentation mask) 偵測橫膈膜 ROI。

    Args:
        image: 2D gray uint8 影像（會被 in-place 修改：filter_top_rows / median_blur）
        config: DiaphragmDetectionConfig 注入所有可控參數
        use_segment: 可選的 paddle segmentation mask（uint8）。提供時繞過古典切割。
        timing: 可選計時累計器（duck-typed，需有 record(stage, dt)）。非 None 時記錄
                binary / candidates / curve_fit / label_loop（REALTIME Layer D）；None 零影響

    Returns:
        DetectionResult
    """
    t = time.perf_counter()
    # 1. Viz canvas（用原圖、不受後續 in-place 影響）
    debug_overlay = cv2.cvtColor(image.copy(), cv2.COLOR_GRAY2BGR)

    # 2. Preprocessing（原邏輯）
    if config.median_blur:
        image = cv2.medianBlur(image, 7)
    filter_top_px = round(config.filter_top_ratio * image.shape[0])
    if filter_top_px > 0:
        image[:filter_top_px, :] = 0

    image_area = image.shape[0] * image.shape[1]
    detect_area_px = round(config.detect_area_ratio * image_area)
    min_use_segment_area_px = round(config.min_use_segment_area_ratio * image_area)

    # 3. Binary：use_segment 路徑 vs 古典切割
    if use_segment is not None:
        _, binary = cv2.threshold(
            use_segment, config.use_segment_background_px, 255, cv2.THRESH_BINARY)
    else:
        binary, _ = algo_segmentation(
            image, use_otsu=config.use_otsu, detect_area=detect_area_px)
    if timing is not None:
        timing.record("binary", time.perf_counter() - t)
        t = time.perf_counter()

    # 4. Candidate filtering
    potential_regions, use_segment_potentials, labels, num_labels = find_candidates(
        binary,
        aspect_ratio_threshold=config.aspect_ratio_threshold,
        area_ratio=config.area_ratio,
        min_use_segment_area=min_use_segment_area_px,
    )
    if timing is not None:
        timing.record("candidates", time.perf_counter() - t)
        t = time.perf_counter()

    # 5. Curve fit 挑最佳
    best_idx: list = []
    regions: list = []
    if len(potential_regions) >= 1:
        best_idx, regions = diaphragm_curve_fit(
            potential_diaphragm_regions=potential_regions,
            labels=labels,
            b_image=binary,
            sections=config.sections,
            prune_branch_max_length=config.prune_branch_max_length,
        )
    if timing is not None:
        timing.record("curve_fit", time.perf_counter() - t)
        t = time.perf_counter()

    # 6. 建輸出 binary 與 viz overlay
    potential_idx = [idx for idx, _, _ in potential_regions]
    filtered_binary = np.zeros(binary.shape, dtype="uint8")
    potential_binary = np.zeros(binary.shape, dtype="uint8")

    for idx in range(1, num_labels):
        color = _OVERLAY_COLORS[idx % len(_OVERLAY_COLORS)]
        if idx in potential_idx:
            color = _COLOR_POTENTIAL
            if idx in best_idx:
                color = _COLOR_BEST
            potential_binary[labels == idx] = 255
        mask = labels == idx
        debug_overlay[mask] = color
        filtered_binary[mask] = 255
    if timing is not None:
        timing.record("label_loop", time.perf_counter() - t)

    # 7. 決定 best_region 與 target_binary（viz 由 visualization.layers.detection 處理）
    if not best_idx:
        return _build_fallback_result(
            config=config,
            image_shape=image.shape,
            use_segment=use_segment,
            use_segment_potentials=use_segment_potentials,
            filtered_binary=filtered_binary,
            potential_binary=potential_binary,
            debug_overlay=debug_overlay,
        )

    # 找到 best
    tops = [t for t, _ in regions]
    bottoms = [b for _, b in regions]
    best_region = (int(np.mean(tops)), int(np.mean(bottoms)))

    target_binary = np.zeros(binary.shape, dtype="uint8")
    target_binary[labels == best_idx[0]] = 255

    # excursion + use_segment 特例：target 改用全部 filtered_binary
    if use_segment is not None and config.phase == Phase.EXCURSION:
        target_binary = filtered_binary

    return DetectionResult(
        best_region=best_region,
        filtered_binary=filtered_binary,
        target_binary=target_binary,
        potential_binary=potential_binary,
        debug_overlay=debug_overlay,
    )


def _build_fallback_result(
    config: DiaphragmDetectionConfig,
    image_shape: tuple,
    use_segment: Optional[np.ndarray],
    use_segment_potentials: list,
    filtered_binary: np.ndarray,
    potential_binary: np.ndarray,
    debug_overlay: np.ndarray,
) -> DetectionResult:
    """curve_fit 沒選出 best 時的 fallback。"""
    fallback_top_px = round(config.fallback_region_top_ratio * image_shape[0])
    best_region = (fallback_top_px, image_shape[0])
    target_binary: Optional[np.ndarray] = None

    if use_segment is not None and use_segment_potentials:
        # 取所有 use_segment 候選的 y union range
        tops = [p[1] for p in use_segment_potentials]
        bottoms = [p[2] for p in use_segment_potentials]
        best_region = (min(tops), max(bottoms))
        if config.phase == Phase.EXCURSION:
            target_binary = filtered_binary

    return DetectionResult(
        best_region=best_region,
        filtered_binary=filtered_binary,
        target_binary=target_binary,
        potential_binary=None,   # 原版 fallback 一律回 None
        debug_overlay=debug_overlay,
    )
