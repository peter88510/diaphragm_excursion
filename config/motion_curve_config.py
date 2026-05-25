"""Motion curve 抽取的使用者層 config。"""
from dataclasses import dataclass


@dataclass
class MotionCurveConfig:
    # 相鄰 x 的 y 差距超過 (image_height × ratio) → 視為斷點
    # 對 955 高影像 = 120 pixel（原 stable_peak 寫死值）
    jump_threshold_ratio: float = 120 / 955

    # 補點搜尋窗：斷點補回時，從 (前一點 y - image_height × ratio) 開始 argmax
    # 對 955 高影像 = 50 pixel
    fix_search_window_ratio: float = 50 / 955

    # Wavelet 平滑等級。原作者開發時試過波峰/波谷用不同 level，後來統一為 3。
    # 保留分別欄位以便未來分化（修改其一即可生效）。
    wavelet_level_trough: int = 3
    wavelet_level_crest: int = 3
