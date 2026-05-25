"""PNG / 一般影像 reader：單檔 或 資料夾。

對外 API：
- read_file(png_path) -> FrameSequence  : 單張 PNG/JPG/BMP
- read_directory(dir_path) -> FrameSequence : 資料夾內所有支援副檔名的影像

設計取捨：
- reader 只負責「讀」。不 resize、不轉色彩空間、不做 PhysicalDelta 預設代入。
- 原 read_png_frame 寫死的 ipad 6 PhysicalDelta（0.023037, 0.005319）已移除。
  PNG 本身不帶 DICOM 等級的物理刻度資訊，呼叫端要顯式提供（透過 config 或
  外掛 metadata），不該由 reader 偷塞預設值（會在多裝置情境下默默算錯）。
- 原 cv2.resize 到 (1500, 955) 也移除。resize 屬於 preprocessing 不屬於 reading。
"""
import os
from typing import List

import cv2
import numpy as np
from natsort import natsorted

from input.frame_sequence import FrameSequence


VALID_IMAGE_SUFFIX = ('.png', '.jpg', '.jpeg', '.bmp')


def read_file(png_path: str) -> FrameSequence:
    if not os.path.isfile(png_path):
        raise FileNotFoundError(f"PNG file not found: {png_path}")

    img = cv2.imread(png_path)  # (H, W, 3) BGR
    if img is None:
        raise ValueError(f"cv2.imread failed (檔案格式損壞或非影像): {png_path}")

    frames = img[np.newaxis, ...]  # (1, H, W, 3)
    return FrameSequence(
        frames=frames,
        source_type='png_file',
        source_path=png_path,
        fps=None,
        metadata={},
    )


def read_directory(dir_path: str) -> FrameSequence:
    if not os.path.isdir(dir_path):
        raise NotADirectoryError(f"Not a directory: {dir_path}")

    image_paths = _list_image_files(dir_path)
    if not image_paths:
        raise RuntimeError(f"No supported image files in: {dir_path}")

    frames_list = []
    for p in image_paths:
        img = cv2.imread(p)
        if img is None:
            raise ValueError(f"cv2.imread failed: {p}")
        frames_list.append(img)

    try:
        frames = np.stack(frames_list)  # (N, H, W, 3)
    except ValueError as e:
        # np.stack 失敗最常見原因：各 frame H/W 不一致
        shapes = [f.shape for f in frames_list]
        raise ValueError(
            f"無法堆疊 PNG frames，各檔尺寸需一致。shapes={shapes[:5]}..."
        ) from e

    return FrameSequence(
        frames=frames,
        source_type='png_dir',
        source_path=dir_path,
        fps=None,
        metadata={'image_paths': image_paths},
    )


def _list_image_files(dir_path: str) -> List[str]:
    """遞迴蒐集資料夾內支援副檔名的影像。沿用原 get_image_list 的過濾規則："""
    paths = []
    for root, _, files in os.walk(dir_path):
        if '.ipynb_checkpoints' in root:
            continue
        if 'label' in root:
            continue
        for f in files:
            if os.path.splitext(f)[1].lower() in VALID_IMAGE_SUFFIX:
                paths.append(os.path.join(root, f))
    return natsorted(paths)
