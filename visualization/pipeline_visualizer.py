"""Pipeline 主入口。

兩條獨立 track（不混用）：
  - debug per stage：dispatch 9B-9D 的 6 個 renderer
  - final overlay：crest/trough 標記 + excursion_cm 文字 + motion curve 軌跡

cfg.enabled=False 時 render_frame() 立刻返回，零 I/O。
"""
import cv2
import numpy as np

from algorithm import FrameResult
from config import ExcursionConfig, VisualizationConfig
from visualization.info_display import excursion_info_display
from visualization.io import final_path, save_png, should_save_final
from visualization.layers.detection import (
    render_detection_pass1,
    render_detection_pass2,
)
from visualization.layers.excursion import render_excursion_brightness
from visualization.layers.motion_curve import render_motion_curve
from visualization.layers.roi_band import render_roi_band
from visualization.layers.segmentation import render_paddle_segmentation


# Final overlay：motion curve 軌跡顏色（debug 用，啞黃避免搶 excursion_info_display 的 markers）
_FINAL_MOTION_COLOR = (0, 180, 180)


class PipelineVisualizer:
    def __init__(
        self,
        cfg: VisualizationConfig,
        excursion_config: ExcursionConfig,
    ):
        self.cfg = cfg
        self.excursion_config = excursion_config

    def render_frame(
        self,
        frame_idx: int,
        image_gray: np.ndarray,
        image_color: np.ndarray,
        seg_mask: np.ndarray,
        frame_result: FrameResult,
    ) -> None:
        if not self.cfg.enabled:
            return

        # ----- debug track（all gray，跟著演算法看到的影像）-----
        render_paddle_segmentation(seg_mask, self.cfg, frame_idx)
        render_detection_pass1(frame_result.detection, self.cfg, frame_idx)
        render_roi_band(
            image_gray, frame_result.y_band,
            frame_result.refined.enhanced_padded,
            self.cfg, frame_idx,
        )
        render_detection_pass2(
            frame_result.refined.padded_overlay, self.cfg, frame_idx)
        render_motion_curve(
            image_gray, frame_result.motion_curve, self.cfg, frame_idx)
        if frame_result.excursion is not None:
            render_excursion_brightness(
                frame_result.motion_curve.diaphragm_p_trough,
                frame_result.motion_curve.diaphragm_p_crest,
                self.excursion_config,
                self.cfg, frame_idx,
            )

        # ----- final track（color base，保留原 DCM 顏色標記）-----
        if should_save_final(self.cfg):
            canvas = self._render_final(image_color, frame_result)
            save_png(canvas, final_path(self.cfg, frame_idx))

    def _render_final(
        self,
        image_color: np.ndarray,
        frame_result: FrameResult,
    ) -> np.ndarray:
        canvas = image_color.copy()

        # motion curve 軌跡（debug 用襯底）
        if self.cfg.final_show_motion_curve:
            for x, y in enumerate(frame_result.motion_curve.init_diaphragm):
                cv2.circle(canvas, (int(x), int(y)), radius=1,
                           color=_FINAL_MOTION_COLOR, thickness=-1)

        # crest/trough markers + excursion 文字（依 toggle 決定要不要叫）
        wants_markers = self.cfg.final_show_peak_markers
        wants_text = self.cfg.final_show_excursion_text
        if frame_result.measurements and (wants_markers or wants_text):
            canvas = excursion_info_display(
                figure=canvas,
                peaks_info=_to_peaks_info(frame_result.measurements),
                font_path=self.cfg.final_font_path,
                peak='ct' if wants_markers else '',
                show_text=wants_text,
            )

        return canvas


def _to_peaks_info(measurements):
    """List[PeakInfo] → legacy peaks_info dict 格式，供 excursion_info_display 使用。

    legacy 格式：
        {idx: {"trough": {"x", "y"}, "crest": {"x", "y"},
               "velocity", "excursion", "time_sec"}}
    """
    return {
        i: {
            "trough": {"x": m.trough[0], "y": m.trough[1]},
            "crest": {"x": m.crest[0], "y": m.crest[1]},
            "velocity": m.velocity,
            "excursion": m.excursion_cm,
            "time_sec": m.time_sec,
        }
        for i, m in enumerate(measurements)
    }
