"""古典影像處理切割（algo_segmentation）。

當不使用 paddle segmenter 時的 fallback path：用 gamma 校正 + 階層量化 + 動態
threshold 找出橫膈膜候選 binary。

Pipeline:
    image (gray uint8)
      → gamma_function          # gamma 2.2 校正
      → level_function          # 量化成 7 階
      → algo_segmentation       # 從最亮階累計到 detect_area → 對應 threshold → binary

直接搬自 patch_code.py，邏輯不動；僅做：
  - 模組常數改 UPPER_CASE
  - 加 docstring / type hints
  - 參數 thresh_otsu → use_otsu（與 DiaphragmDetectionConfig 對齊）
"""
from collections import Counter
from typing import Tuple

import cv2
import numpy as np


# 階層量化表
# CHOICES_LV    : 階層編號（0 最暗、6 最亮）
# CHOICES_VALUE : 該階對應的灰階值上界（gamma 校正後的閾值）
CHOICES_LV = [0, 1, 2, 3, 4, 5, 6]
CHOICES_VALUE = [40, 60, 140, 170, 205, 220, 255]


def gamma_function(pixel_array: np.ndarray, gamma: float = 2.2) -> np.ndarray:
    """Gamma 校正。輸入 0-255、輸出 0-255 float。"""
    normalized = pixel_array / 255.0
    corrected = np.power(normalized, 1 / gamma)
    return corrected * 255


def level_function(gamma_image: np.ndarray) -> np.ndarray:
    """把 gamma 校正後的影像量化成 0~6 階。"""
    condition = [gamma_image <= value for value in CHOICES_VALUE]
    level_image = np.select(condition, CHOICES_LV, 0).astype(np.uint8)
    return level_image


def algo_segmentation(
    image: np.ndarray,
    use_otsu: bool,
    detect_area: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """古典 binary segmentation。

    Args:
        image: gray uint8 影像
        use_otsu: True → 直接用 OTSU；False → 走階層累計法
        detect_area: 階層累計法的目標像素數量（從最亮階往下累積，達標即停）

    Returns:
        (binary, value_image)
        binary      : 0/255 uint8 mask
        value_image : 階層量化的視覺化影像（debug / overlay 用）
    """
    gamma_image = gamma_function(image)
    level_image = level_function(gamma_image)

    counter_dict = Counter(level_image.flatten())

    count = 0
    cumulate = {}
    thresh = 0
    for i in range(len(CHOICES_LV) - 1, -1, -1):
        c = counter_dict.get(i, 0)
        count += c
        cumulate[i] = count
        if count >= detect_area:
            thresh = CHOICES_VALUE[i] - 1
            break

    condition = [level_image == value for value in CHOICES_LV]
    value_image = np.select(condition, CHOICES_VALUE, 0).astype(np.uint8)

    if use_otsu:
        _, binary = cv2.threshold(
            image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        # 注意：thresh 為「不包含」上界，所以 value-1 表示「該階以上」
        _, binary = cv2.threshold(value_image, thresh, 255, cv2.THRESH_BINARY)

    return binary, value_image
