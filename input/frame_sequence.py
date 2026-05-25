"""統一的 frame 序列容器。

所有 input reader（dicom / png 單檔 / png 資料夾）都產出 FrameSequence。
下游演算法 / 視覺化只透過這個型別取得 frames 與 metadata，
不必再分 single-frame / multi-frame、PNG / DICOM 的條件分支。

設計約束：
- frames 首維永遠是 N（single-frame 也包成 N=1）→ 下游 for-loop 一致
- 通道資訊保留原始（gray 是 (N,H,W)；color 是 (N,H,W,3)）
- 演算法需要灰階用 .as_gray()，視覺化需要彩色用 .as_color()
- metadata 用 dict（彈性、不同 source 欄位不同）
"""
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np


@dataclass
class FrameSequence:
    frames: np.ndarray                              # (N, H, W) 或 (N, H, W, 3)
    source_type: str                                # 'png_file' / 'png_dir' / 'dcm_single' / 'dcm_multi'
    source_path: str                                # 原始檔案或資料夾路徑
    fps: Optional[float] = None                     # multi-frame 才有意義（DCM CineRate）
    metadata: dict = field(default_factory=dict)    # PhysicalDeltaY/X、region_location 等

    def __post_init__(self):
        if self.frames.ndim not in (3, 4):
            raise ValueError(
                f"frames 必須是 (N,H,W) 或 (N,H,W,3)，實得 shape={self.frames.shape}"
            )
        if self.frames.ndim == 4 and self.frames.shape[-1] not in (1, 3, 4):
            raise ValueError(
                f"frames 第 4 維（channel）必須是 1/3/4，實得 {self.frames.shape[-1]}"
            )

    @property
    def is_color(self) -> bool:
        return self.frames.ndim == 4 and self.frames.shape[-1] >= 3

    def as_gray(self) -> np.ndarray:
        """回傳 (N, H, W) 灰階 array。已是 gray 直接回傳原 frames（zero-copy）。"""
        if not self.is_color:
            return self.frames
        # BGR2GRAY 對應 cv2 慣例（與 paddleseglibs 內部 BGR2RGB 配對使用一致）
        return np.stack(
            [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in self.frames]
        )

    def as_color(self) -> np.ndarray:
        """回傳 (N, H, W, 3) 彩色 array。已是 color 直接回傳原 frames（zero-copy）。"""
        if self.is_color:
            return self.frames
        # gray → 3 通道複製（給視覺化疊圖用）
        return np.stack([self.frames] * 3, axis=-1)
