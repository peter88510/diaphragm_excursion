"""ROI band 影像強化。

直接搬自 patch_code.py 的 complementary_enhancing，差別：
  - 預設 num_segments 從 3 改 1，對齊 caller 實際使用值
  - 移除註解掉的 matplotlib 直方圖 / cv2.imshow / threshold 實驗 code
    （這些是註解掉的開發實驗、非保留 fallback；Step 6 viz 統整時走另套機制）
  - original_img 隨之移除（先前只供 commented viz 使用）
  - 加 docstring / type hints
"""
from typing import Tuple

import numpy as np


def enhance_band(
    image: np.ndarray,
    band: Tuple[int, int],
    num_segments: int = 1,
) -> Tuple[np.ndarray, np.ndarray]:
    """對 image 的 vertical band 區域做變分增強。

    演算法 (per segment):
        s = clip(2 - x, 0, 1)
        phi = (s * x) ** 2
        enhanced = clip(x * (s + phi), 0, 1)

    Args:
        image: 2D gray uint8 影像
        band: (top, bottom) y 範圍
        num_segments: 水平方向切幾段獨立強化

    Returns:
        (padded, enhanced_band)
        padded        : shape (h, w)，原圖大小、僅 band 區域填強化結果（其餘為 0）
        enhanced_band : shape (bottom-top, w)，純強化結果（給下游再 detect 用）
    """
    h, w = image.shape[:2]
    padded = np.zeros((h, w), dtype=np.uint8)

    top, bottom = band
    band_image = image[top:bottom, :].astype(np.float32) / 255.0

    segment_width = w // num_segments
    segments_output = []
    for i in range(num_segments):
        start_x = i * segment_width
        end_x = start_x + segment_width if i < num_segments - 1 else w
        segment = band_image[:, start_x:end_x]

        s = np.clip(2.0 - segment, 0, 1)
        phi = (s * segment) ** 2
        enhanced = np.clip(segment * (s + phi), 0, 1)

        segments_output.append((enhanced * 255).astype(np.uint8))

    enhanced_band = np.hstack(segments_output)
    padded[top:bottom, :] = enhanced_band
    return padded, enhanced_band
