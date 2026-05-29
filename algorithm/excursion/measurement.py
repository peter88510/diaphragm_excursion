"""Peak/Trough 位置 → 物理量計算（excursion_cm / time_sec / velocity）。

重構自舊版 root util 的 excursion_time_calculator，重整後：
  - 5-tuple 回傳 → PeakInfo dataclass
  - velocity div-by-zero 安全處理（返 None 而非 crash）
  - 移除 `print("[][][] SCALE Y ...")` 噪音
  - 命名 compute_peak_info（原名混淆「time_calculator」實則三項全算）

Phase 策略：
  Excursion phase 在 main.py 不傳 scale_x → time_sec / velocity = None
  Sniff phase 提供 scale_x → 計算 time_sec / velocity
"""
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class PeakInfo:
    crest: Tuple[int, int]                # (x, y)
    trough: Tuple[int, int]               # (x, y)
    excursion_pixel: int                  # |crest_y - trough_y| + 1
    excursion_cm: Optional[float]         # scale_y is None → None
    time_pixel: int                       # |crest_x - trough_x| + 1
    time_sec: Optional[float] = None      # scale_x is None 或 time_pixel=0 → None
    velocity: Optional[float] = None      # time_sec is None 或 0 → None


def compute_peak_info(
    crest: Tuple[int, int],
    trough: Tuple[int, int],
    scale_y: Optional[float] = None,
    scale_x: Optional[float] = None,
) -> PeakInfo:
    """從 (x,y) peak/trough 位置計算 excursion 物理量。

    Args:
        crest: (x, y) of crest
        trough: (x, y) of trough
        scale_y: cm per pixel (vertical)。None → excursion_cm 為 None
        scale_x: sec per pixel (horizontal)。
            None → time_sec / velocity 皆 None（excursion phase 情境）
            提供 → 計算 time_sec；非 0 才算 velocity（sniff phase 情境）

    Returns:
        PeakInfo
    """
    # +1 是原版註解「上下邊界手標時預設標邊界外」的補償；+0 是保留 padding 預留位
    excursion_pixel = abs(crest[1] - trough[1]) + 1
    time_pixel = abs(crest[0] - trough[0]) + 1

    excursion_cm: Optional[float] = (
        round(excursion_pixel * scale_y, 2) if scale_y is not None else None
    )

    time_sec: Optional[float] = None
    velocity: Optional[float] = None
    if scale_x is not None and time_pixel > 0:
        time_sec = round(time_pixel * scale_x, 2)
        if time_sec > 0 and excursion_cm is not None:
            velocity = round(excursion_cm / time_sec, 2)

    return PeakInfo(
        crest=crest,
        trough=trough,
        excursion_pixel=excursion_pixel,
        excursion_cm=excursion_cm,
        time_pixel=time_pixel,
        time_sec=time_sec,
        velocity=velocity,
    )
