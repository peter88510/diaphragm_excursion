"""GLOBAL_WINDOW mode 的 final overlay viz。

風格完全沿用 single-frame final（PipelineVisualizer._render_final）：
  - canvas base = 兩 keyframe color 影像依 first/second 拼接
  - motion curve 啞黃軌跡（cfg.final_show_motion_curve）
  - crest/trough markers + excursion 文字（excursion_info_display）

輸出：{output_dir}/global/final.png（單一檔）。
"""
import cv2
import numpy as np

from algorithm.multiframe.global_window import GlobalExcursionResult
from config import ExcursionConfig, VisualizationConfig
from visualization.info_display import excursion_info_display
from visualization.io import global_final_path, save_png, should_save_final
from visualization.pipeline_visualizer import _FINAL_MOTION_COLOR, _to_peaks_info


def render_global_final(
    global_result: GlobalExcursionResult,
    image_color_first: np.ndarray,
    image_color_second: np.ndarray,
    cfg: VisualizationConfig,
    excursion_cfg: ExcursionConfig,
) -> None:
    """渲染 GLOBAL_WINDOW final overlay。gated by `should_save_final`。"""
    if not should_save_final(cfg):
        return

    lf = global_result.first_segment_len_px
    ls = global_result.second_segment_len_px
    canvas = np.concatenate(
        [image_color_first[:, :lf], image_color_second[:, -ls:]], axis=1
    )

    if cfg.final_show_motion_curve:
        for x, y in enumerate(global_result.stitched_init_diaphragm):
            cv2.circle(canvas, (int(x), int(y)), radius=1,
                       color=_FINAL_MOTION_COLOR, thickness=-1)

    wants_markers = cfg.final_show_peak_markers
    wants_text = cfg.final_show_excursion_text
    if global_result.measurements and (wants_markers or wants_text):
        canvas = excursion_info_display(
            figure=canvas,
            peaks_info=_to_peaks_info(global_result.measurements),
            font_path=cfg.final_font_path,
            peak='ct' if wants_markers else '',
            show_text=wants_text,
        )

    save_png(canvas, global_final_path(cfg))
