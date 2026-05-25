"""逐 frame 處理的彙整 result。

從 segmentation → diaphragm detection → ROI band → motion curve → excursion → measurement
整條 pipeline 的單一 frame 輸出聚合成這個 dataclass。

各欄位來源：
  detection       : algorithm.diaphragm_detection.detect 第一次（吃 paddle seg）
  y_band          : algorithm.roi_band.compute_target_y_range
  refined         : algorithm.roi_band.enhanced_search 第二次 detect（強化古典路徑）
  selection       : algorithm.roi_band.select_target 選定 target / mask
  motion_curve    : algorithm.motion_curve.extract_motion_curve
  excursion       : algorithm.excursion.brightness_way（excursion phase 才填）
  measurements    : algorithm.excursion.compute_peak_info per batch（physical 量）

跨 frame 撈指定 frame 做合併分析：直接用 results[i] / results[j]，
不需要另設 test_info dict。
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from algorithm.diaphragm_detection import DetectionResult
from algorithm.excursion import ExcursionResult, PeakInfo
from algorithm.motion_curve import MotionCurveResult
from algorithm.roi_band import RoiSearchResult, TargetSelection


@dataclass
class FrameResult:
    detection: DetectionResult
    y_band: Tuple[int, int]
    refined: RoiSearchResult
    selection: TargetSelection
    motion_curve: MotionCurveResult
    excursion: Optional[ExcursionResult] = None
    measurements: List[PeakInfo] = field(default_factory=list)
