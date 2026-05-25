"""DICOM region crop preprocessing。

從原 main.py 的 CropProcess 抽出，介面改吃 FrameSequence。

關鍵修正 vs 原版：
- 不再依賴 pydicom 原始物件（從 metadata['region_location'] 取座標）
- multi-frame DCM 自動正確：只 slice H/W，N 維永遠保留
  → 修掉原版「multi-frame 被切空」的 bug
- 非 DCM source（PNG / 缺 region 欄位 DCM）→ 直接 pass-through

參數來源：吃 DicomCropConfig（ruler / black_padding）。default 與原 hardcode 完全一致。
"""
from dataclasses import replace

from config.dicom_crop_config import DicomCropConfig
from input.frame_sequence import FrameSequence


def apply_dicom_crop(
    seq: FrameSequence,
    cfg: DicomCropConfig,
) -> FrameSequence:
    """對含 region_location metadata 的 FrameSequence 套用裁切。

    Args:
        seq: 來自 reader 的 FrameSequence
        cfg: DicomCropConfig（ruler / black_padding）

    Returns:
        新的 FrameSequence，frames 已裁切；metadata / source_type / fps 不變。
        若無 region_location，原樣回傳（no-op）。
    """
    if 'region_location' not in seq.metadata:
        return seq

    rl = seq.metadata['region_location']

    y_start = rl['min_y0'] + cfg.ruler
    y_end = rl['max_y1'] + 1
    x_start = rl['min_x0'] + cfg.black_padding + cfg.ruler
    x_end = rl['max_x1'] + cfg.black_padding + 1

    # frames 首維永遠是 N（FrameSequence 約束）
    # 只 slice H/W 兩維，色彩通道（若有）保留
    if seq.frames.ndim == 3:
        cropped = seq.frames[:, y_start:y_end, x_start:x_end]
    else:  # ndim == 4
        cropped = seq.frames[:, y_start:y_end, x_start:x_end, :]

    if cropped.size == 0:
        raise ValueError(
            f"Crop 結果為空。檢查 region_location 與 cfg 參數。"
            f" frames.shape={seq.frames.shape}, "
            f"y=[{y_start}:{y_end}], x=[{x_start}:{x_end}]"
        )

    return replace(seq, frames=cropped)
