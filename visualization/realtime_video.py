"""REALTIME canvas → mp4 incremental writer（imageio-ffmpeg backend, H.264 libx264）。

skip 幀 carry-forward 上一張 canvas；pre-bootstrap 用原始 color frame 補位
（不污染 carry-forward）。

品質：libx264 + `quality` 參數（imageio 0-10 scale，default 8 ≈ CRF 20，
高品質中等檔案大小，醫療影像場景平衡）；之後要更高品質可上調至 9-10。

依賴：`imageio` + `imageio-ffmpeg`（ffmpeg binary 自帶；首次使用會解壓 ~20MB）。
安裝：`pip install imageio imageio-ffmpeg`。

caller pattern:
    with RealtimeVideoWriter(path, fps, W, H) as vw:
        for i in range(...):
            if skip:
                if not vw.write_skip():       # 無 last → caller 補 placeholder
                    vw.write_placeholder(color_frames[i])
                continue
            canvas = render_realtime_canvas(...)
            vw.write(canvas)
"""
import logging
from pathlib import Path
from typing import Optional

import cv2
import imageio
import numpy as np

log = logging.getLogger(__name__)


# imageio quality scale 0-10；8 ≈ CRF 20（高品質、適合臨床檢視；可調 9-10 拉滿）
_DEFAULT_QUALITY = 8


class RealtimeVideoWriter:
    """imageio-ffmpeg incremental writer：carry-forward / placeholder semantics。

    輸入幀為 cv2 BGR uint8；內部 BGR→RGB 後送給 imageio（ffmpeg 預期 RGB）。

    **偶數對齊**：libx264 + yuv420p（最高相容性）要求 W/H 皆為偶數。canvas
    若有奇數維度（例如 700×445）→ 內部 pad 黑邊到偶數（700×446）；下緣 1px
    黑邊視覺上無感，pixel data 完整保留。
    """

    def __init__(
        self,
        output_path: Path,
        fps: float,
        width: int,
        height: int,
        quality: int = _DEFAULT_QUALITY,
    ):
        self._path = output_path
        self._fps = fps
        self._quality = quality
        # 對齊到偶數（yuv420p 要求）；多出的 row/col 寫 0（黑）
        self._src_h = height
        self._src_w = width
        self._dst_h = height + (height & 1)
        self._dst_w = width + (width & 1)
        self._needs_pad = (self._dst_h != self._src_h) or (self._dst_w != self._src_w)
        self._writer = None
        self._last_rgb: Optional[np.ndarray] = None

    def __enter__(self) -> "RealtimeVideoWriter":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # macro_block_size=1：允許任意解析度（W/H 偶數對齊已自己處理）
        self._writer = imageio.get_writer(
            str(self._path),
            fps=self._fps,
            codec="libx264",
            quality=self._quality,
            macro_block_size=1,
        )
        return self

    def _pad_to_even(self, rgb: np.ndarray) -> np.ndarray:
        """pad 到偶數 W/H；已是偶數則直接回傳（不複製）。"""
        if not self._needs_pad:
            return rgb
        padded = np.zeros((self._dst_h, self._dst_w, 3), dtype=rgb.dtype)
        padded[:self._src_h, :self._src_w] = rgb
        return padded

    def write(self, frame: np.ndarray) -> None:
        """正常 ingested 幀；BGR→RGB→pad 後寫入並記入 last 供後續 carry-forward。"""
        rgb = self._pad_to_even(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        self._writer.append_data(rgb)
        self._last_rgb = rgb

    def write_skip(self) -> bool:
        """skip 幀 carry-forward。

        Returns:
            True：成功 carry-forward 上一張 canvas。
            False：尚未有 last（pre-bootstrap）；caller 應改用 write_placeholder。
        """
        if self._last_rgb is None:
            return False
        self._writer.append_data(self._last_rgb)
        return True

    def write_placeholder(self, raw: np.ndarray) -> None:
        """pre-bootstrap：用原始 color frame 補位；**不污染 last**（避免之後 carry 到 raw）。"""
        rgb = self._pad_to_even(cv2.cvtColor(raw, cv2.COLOR_BGR2RGB))
        self._writer.append_data(rgb)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
