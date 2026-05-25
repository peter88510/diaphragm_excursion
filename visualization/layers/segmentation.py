"""Paddle segmentation mask 的 debug 渲染。"""
import numpy as np

from config.visualization_config import VisualizationConfig
from visualization import stages
from visualization.io import debug_path, save_png, should_save_debug


def render_paddle_segmentation(
    seg_mask: np.ndarray,
    cfg: VisualizationConfig,
    frame_idx: int,
) -> None:
    """存 paddle segmenter 輸出的 raw mask（單通道 uint8）。"""
    if not should_save_debug(cfg, stages.PADDLE_SEGMENTATION):
        return
    save_png(seg_mask, debug_path(cfg, stages.PADDLE_SEGMENTATION, frame_idx))
