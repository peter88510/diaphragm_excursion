"""Segmenter 抽象介面。

任何要插入演算法 pipeline 的 segmenter（PaddleSeg / ONNX / TensorRT / ...）
都實作這個 ABC。換平台時新增子類別，呼叫端不必改動。

NOTE: 目前 predict() 接受 (image_path, dcm_array) 的雙參數介面，是為了
與舊 paddleseglibs/predict.py 內部的副檔名分支邏輯相容。
在 Step 3 引入 FrameSequence 後，會把這個介面改成 predict(frame_sequence)。
"""
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np
from PIL import Image


class SegmenterBase(ABC):
    @abstractmethod
    def load(self) -> None:
        """一次性 setup：建 model、load weights、建 transforms。

        重複呼叫應為冪等（idempotent）：第二次呼叫不應重新 load 權重。
        """
        ...

    @abstractmethod
    def predict(
        self,
        image_path: str,
        dcm_array: Optional[np.ndarray] = None,
    ) -> Image.Image:
        """跑單張影像推論。

        Args:
            image_path: 影像檔路徑。即使 dcm_array 已提供仍需傳入，
                因 paddleseglibs 內部用副檔名決定讀檔分支。
            dcm_array: 已從 DICOM 取出的 pixel array（3-channel 或 grayscale）。
                .dcm / .DICOM 副檔名時必填；其他副檔名時忽略。

        Returns:
            PIL.Image.Image，mode='P'（pseudo-color label mask）。
            與舊 paddleseglibs.predict.infer() 回傳型別一致。
        """
        ...
