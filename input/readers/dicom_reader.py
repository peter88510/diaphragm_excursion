"""DICOM reader：single / multi frame 統一處理。

對外只暴露 `read(dcm_path)`。內部依 `NumberOfFrames` 判斷單張或多張，
把 pixel_array 標準化為 (N, H, W) 或 (N, H, W, C)，包成 FrameSequence。

行為相容性：
- `SequenceOfUltrasoundRegions[1]` 維持原 main.py 的 index `1`
- PhysicalDeltaY/X、RegionLocation 取得方式與原 read_dicom_frames / CropProcess 一致

Domain note：
- 本系統處理的 DCM 上半為 B-mode（2D 影像）、下半為 M-mode（時間軸掃描）
- `SequenceOfUltrasoundRegions[0]` = B-mode 區塊
- `SequenceOfUltrasoundRegions[1]` = M-mode 區塊 ← 橫膈膜 excursion 計算用此區塊
  因此 `_REGION_INDEX = 1`
"""
import os
from typing import Optional

import numpy as np
import pydicom

from input.frame_sequence import FrameSequence


_REGION_INDEX = 1   # M-mode region（excursion 計算依據）；index 0 是 B-mode


def read(dcm_path: str) -> FrameSequence:
    if not os.path.isfile(dcm_path):
        raise FileNotFoundError(f"DICOM file not found: {dcm_path}")

    dcm = pydicom.dcmread(dcm_path)
    pixel_array = dcm.pixel_array

    n_frames = int(getattr(dcm, 'NumberOfFrames', 1))
    is_multi = n_frames > 1

    frames = _normalize_frames_shape(pixel_array, is_multi)

    metadata = _extract_metadata(dcm)
    fps = _extract_fps(dcm) if is_multi else None

    return FrameSequence(
        frames=frames,
        source_type='dcm_multi' if is_multi else 'dcm_single',
        source_path=dcm_path,
        fps=fps,
        metadata=metadata,
    )


def _normalize_frames_shape(pixel_array: np.ndarray, is_multi: bool) -> np.ndarray:
    """確保 frames 首維永遠是 N。

    - multi-frame：信任 pydicom 慣例，首維本就是 N
    - single-frame：(H,W) 或 (H,W,C) → 加一維包成 N=1
    """
    if is_multi:
        if pixel_array.ndim < 3:
            raise ValueError(
                f"Multi-frame DCM 但 pixel_array.ndim={pixel_array.ndim}，預期 >= 3"
            )
        return pixel_array

    if pixel_array.ndim in (2, 3):
        return pixel_array[np.newaxis, ...]
    # 4D 但 NumberOfFrames=1，視為已包好的 (1, H, W, C)
    return pixel_array


def _extract_metadata(dcm) -> dict:
    """取出下游可能用到的 DICOM metadata。缺欄位就略過，不 raise。"""
    metadata = {}
    region = _get_region(dcm)
    if region is None:
        return metadata

    if hasattr(region, 'PhysicalDeltaY'):
        metadata['physical_delta_y'] = float(region.PhysicalDeltaY)
    if hasattr(region, 'PhysicalDeltaX'):
        metadata['physical_delta_x'] = float(region.PhysicalDeltaX)

    region_attrs = (
        'RegionLocationMinX0', 'RegionLocationMaxX1',
        'RegionLocationMinY0', 'RegionLocationMaxY1',
    )
    if all(hasattr(region, a) for a in region_attrs):
        metadata['region_location'] = {
            'min_x0': int(region.RegionLocationMinX0),
            'max_x1': int(region.RegionLocationMaxX1),
            'min_y0': int(region.RegionLocationMinY0),
            'max_y1': int(region.RegionLocationMaxY1),
        }
    return metadata


def _get_region(dcm):
    """取 SequenceOfUltrasoundRegions[_REGION_INDEX]，不存在就回 None。"""
    seq = getattr(dcm, 'SequenceOfUltrasoundRegions', None)
    if seq is None:
        return None
    try:
        return seq[_REGION_INDEX]
    except IndexError:
        return None


def _extract_fps(dcm) -> Optional[float]:
    """multi-frame 的播放速率。RecommendedDisplayFrameRate > CineRate 優先。"""
    for attr in ('RecommendedDisplayFrameRate', 'CineRate'):
        if hasattr(dcm, attr):
            return float(getattr(dcm, attr))
    return None
