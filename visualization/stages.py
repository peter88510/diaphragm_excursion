"""Debug stage 名稱常數。

集中管理 stage 字串，避免拼字錯誤散落各 layer。
檔名規則：output/debug/{stage}/{i:04d}.png

對應 Patch 9B-9D 的 layer 輸出：
  9B：detection pass1 三張
  9C：roi band 兩張
  9D：detection pass2 / motion curve / brightness 波形
另外加入 paddle segmentation mask（segmenter 輸出原圖）
"""
from typing import FrozenSet

# 9B — detection pass1
PADDLE_SEGMENTATION = "paddle_segmentation"
DETECTION_PASS1_OVERLAY = "detection_pass1_overlay"
DETECTION_PASS1_FILTERED = "detection_pass1_filtered"
DETECTION_PASS1_POTENTIAL = "detection_pass1_potential"

# 9C — roi band
ROI_BAND_YBAND = "roi_band_yband"
ROI_BAND_ENHANCED = "roi_band_enhanced"

# 9D — pass2 + motion curve + excursion
DETECTION_PASS2_OVERLAY = "detection_pass2_overlay"
MOTION_CURVE = "motion_curve"
EXCURSION_BRIGHTNESS = "excursion_brightness"


ALL_STAGES: FrozenSet[str] = frozenset({
    PADDLE_SEGMENTATION,
    DETECTION_PASS1_OVERLAY,
    DETECTION_PASS1_FILTERED,
    DETECTION_PASS1_POTENTIAL,
    ROI_BAND_YBAND,
    ROI_BAND_ENHANCED,
    DETECTION_PASS2_OVERLAY,
    MOTION_CURVE,
    EXCURSION_BRIGHTNESS,
})
