"""PaddleSeg segmenter 的使用者層 config。

設計原則：
- 與 algorithm/ 完全分離：algorithm 不該 import 任何寫死的 model 路徑或 inference 旗標
- 與 paddleseglibs/ 解耦：使用者只需碰這個檔，不必進 paddleseglibs 內部
- 平台專屬：未來換 ONNX / TensorRT 時新增 `onnx_config.py`、`tensorrt_config.py`，
  「換平台」由 algorithm/segmentation/base.py 的抽象介面保證，不靠統一 Config 型別
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

from paddleseglibs.predict import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_MODEL_PATH,
    DEFAULT_SAVE_DIR,
)


@dataclass
class PaddleSegSegmenterConfig:
    # --- Model ---
    config_path: str = DEFAULT_CONFIG_PATH
    model_path: str = DEFAULT_MODEL_PATH
    device: Optional[str] = None  # 'gpu' / 'cpu' / None=auto

    # --- Inference ---
    resize_ratio: float = 1.0

    # --- Augmentation (test-time) ---
    aug_pred: bool = False
    scales: float = 1.0
    flip_horizontal: bool = False
    flip_vertical: bool = False

    # --- Sliding window ---
    is_slide: bool = False
    crop_size: Optional[Tuple[int, int]] = None
    stride: Optional[Tuple[int, int]] = None

    # --- Misc ---
    custom_color: Optional[List[int]] = None

    # --- Output side-effects ---
    # 預設 False：不寫 PNG 到磁碟。原 paddleseglibs 預設行為是強制存檔，
    # 對非 batch 場景（如 video frame loop）會產生大量垃圾檔，故此處反轉預設。
    save_predictions: bool = False
    save_dir: str = DEFAULT_SAVE_DIR
