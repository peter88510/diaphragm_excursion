"""PaddleSeg 的 SegmenterBase 實作。

封裝 paddleseglibs.predict.build_predictor + predict_one：
  - Model weights 在 load() 時載入一次
  - predict() 重複呼叫共用同一份權重（不再每次重 load）
  - 透過 PaddleSegSegmenterConfig 注入所有可控參數，與 algorithm 邏輯解耦
"""
from typing import Optional

import numpy as np
from PIL import Image

from algorithm.segmentation.base import SegmenterBase
from config.paddleseg_config import PaddleSegSegmenterConfig
from paddleseglibs.predict import build_predictor, predict_one


class PaddleSegSegmenter(SegmenterBase):
    def __init__(self, config: PaddleSegSegmenterConfig):
        self._cfg = config
        self._predictor = None

    def load(self) -> None:
        if self._predictor is not None:
            return
        self._predictor = build_predictor(
            config_path=self._cfg.config_path,
            model_path=self._cfg.model_path,
            device=self._cfg.device,
            save_dir=self._cfg.save_dir,
            resize_ratio=self._cfg.resize_ratio,
            aug_pred=self._cfg.aug_pred,
            scales=self._cfg.scales,
            flip_horizontal=self._cfg.flip_horizontal,
            flip_vertical=self._cfg.flip_vertical,
            is_slide=self._cfg.is_slide,
            stride=self._cfg.stride,
            crop_size=self._cfg.crop_size,
            custom_color=self._cfg.custom_color,
            save_predictions=self._cfg.save_predictions,
        )

    def predict(
        self,
        image_path: str,
        dcm_array: Optional[np.ndarray] = None,
    ) -> Image.Image:
        if self._predictor is None:
            self.load()
        return predict_one(
            self._predictor,
            image_path=image_path,
            dcm_array=dcm_array,
            image_dir=None,
        )
