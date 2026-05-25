"""多組 PeakInfo → 單值聚合接口。

GLOBAL_WINDOW / multi-batch 場景：一張 final overlay 上需要一個代表性的
excursion 數值。本檔提供 stub 入口；具體聚合規則待定（mean / median /
max-excursion / first 等），實作後加 cfg 切換。

目前行為：fallback 回第 0 組（與 Patch 13C 前的 `peaks_info[0]` 等值）。
"""
from typing import List, Optional

from algorithm.excursion.measurement import PeakInfo


def aggregate_measurements(
    measurements: List[PeakInfo],
) -> Optional[PeakInfo]:
    """List[PeakInfo] → 單一代表性 PeakInfo。

    Stub：目前回第 0 組；measurements 空回 None。
    待定義聚合規則（mean / median / max / first）後在此擴充並加 cfg。
    """
    if not measurements:
        return None
    return measurements[0]
