"""Diaphragm detection layer 的使用者層 config。

與 `paddleseg_config.py` 同級：使用者層的設定入口、與 algorithm 實作解耦。
algorithm/diaphragm_detection/ 內部消費這個 config，不該硬編碼預設值。

Phase 是使用者語意（不同臨床任務），不同 phase 對應不同 sections / aspect_ratio
等推薦預設值，透過 `DiaphragmDetectionConfig.for_phase()` 取得。
"""
from dataclasses import dataclass
from enum import Enum


class Phase(Enum):
    SNIFF = 'sniff'
    EXCURSION = 'excursion'
    OTHER = 'other'


@dataclass
class DiaphragmDetectionConfig:
    # --- Phase-driven defaults ---
    phase: Phase = Phase.EXCURSION
    sections: int = 1
    aspect_ratio_threshold: float = 4.0

    # --- 古典切割（algo_segmentation；不使用 paddle mask 時的 fallback） ---
    # 階層累計法目標像素數（從最亮階往下累積到此值對應的 threshold）
    # 對 955×1500 canonical = 20000 pixel
    detect_area_ratio: float = 20000 / (955 * 1500)
    use_otsu: bool = False

    # --- 通用前處理 ---
    median_blur: bool = True
    # 最上面幾列清為 0（標尺雜訊區）。對 955 高影像 = 100 pixel
    filter_top_ratio: float = 100 / 955

    # --- use_segment 路徑（paddle mask 二值化參數） ---
    use_segment_background_px: int = 38    # 大於此值視為前景
    # use_segment fallback 過濾微小切割的最小面積
    # 對 955×1500 canonical = 1000 pixel
    min_use_segment_area_ratio: float = 1000 / (955 * 1500)

    # --- 候選篩選 ---
    # 候選必須佔整圖面積 > ratio。對應 canonical 1500×955 ~ 10000 pixel² 設計
    area_ratio: float = 10000 / (955 * 1500)
    # 沒找到時的 default region 上緣。對 955 高影像 = 200 pixel
    fallback_region_top_ratio: float = 200 / 955

    # --- curve_fit ---
    prune_branch_max_length: int = 100         # 原 while length < 100

    @classmethod
    def for_phase(cls, phase: Phase) -> "DiaphragmDetectionConfig":
        """根據 phase 自動填入 sections / aspect_ratio 預設。

        對應原 patch_code.py __main__ 內的 phase→param 推導邏輯，
        差別是 type-safe（不再字串比較）。其他欄位走 dataclass 預設。
        """
        if phase == Phase.SNIFF:
            return cls(phase=phase, sections=6, aspect_ratio_threshold=6.0)
        if phase == Phase.EXCURSION:
            return cls(phase=phase, sections=1, aspect_ratio_threshold=4.0)
        return cls(phase=phase, sections=2, aspect_ratio_threshold=10000.0)
