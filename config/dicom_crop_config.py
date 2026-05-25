"""DICOM region crop preprocessing config。

對應 `input/preprocessing/dicom_crop.py::apply_dicom_crop` 的可調參數。
與其他 per-layer cfg 同位階；掛在 RunBundle.dicom_crop。

預設值對齊原 module-level `DEFAULT_RULER` / `DEFAULT_BLACK_PADDING`，零行為差異。
"""
from dataclasses import dataclass


@dataclass
class DicomCropConfig:
    # 上方 / 左側留白寬度（pixel）— 對應 region_location 內框
    ruler: int = 20

    # 左側額外 padding（pixel）— 避開部分 vendor 的黑邊
    black_padding: int = 0
