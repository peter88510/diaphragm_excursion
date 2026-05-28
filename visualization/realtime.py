"""REALTIME mode 雙 track viz。

兩個獨立 track（每 frame 各一張 PNG）：
  - canvas track：當下 frame[i] 視窗 + single-frame overlay（同 LEGACY final 風格）
                  → {output_dir}/realtime/canvas/{i:04d}.png
  - global track：累積拼接 canvas（frame[1..i] 各取 color 右尾 stride）+ 全局 overlay
                  → {output_dir}/realtime/global/{i:04d}.png

Warmup gating（is_warmup 由 main 判定 frame_idx < warmup_frames）：
  - warmup 期：只顯示 image + "warming up i/N" 文字，不疊 overlay
  - global track 額外：過 warmup 但累積 width 未達 algorithm_min_width（state.excursion=None）
    → 顯示 "computing..."

px / 字型 ratio 化沿用 info_display（ref height-relative）；status 文字 ratio 同基準。
"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from algorithm.multiframe.realtime import RealtimeState
from config import ExcursionConfig, VisualizationConfig
from visualization.info_display import excursion_info_display
from visualization.io import (
    realtime_canvas_path,
    realtime_global_path,
    save_png,
    should_save_realtime,
)
from visualization.pipeline_visualizer import _FINAL_MOTION_COLOR


# status 文字（ref 1500×955；以 image height 為基準）
_REF_HEIGHT = 955
_RATIO_STATUS_FONT = 28 / _REF_HEIGHT
_RATIO_STATUS_STROKE = 2 / _REF_HEIGHT
_RATIO_STATUS_TOP = 0.08          # 文字垂直位置（image height 比例）
_STATUS_TEXT_COLOR = (255, 255, 255)
_STATUS_STROKE_FILL = (0, 0, 0)


def render_realtime_canvas(
    frame_idx: int,
    image_color: np.ndarray,
    frame_result,
    is_warmup: bool,
    warmup_total: int,
    cfg: VisualizationConfig,
    excursion_cfg: ExcursionConfig,
) -> None:
    """當下視窗 track：frame[i] image + single-frame overlay（或 warmup 文字）。"""
    if not should_save_realtime(cfg):
        return

    canvas = image_color.copy()
    if is_warmup:
        canvas = _draw_status_text(
            canvas, f"warming up {frame_idx}/{warmup_total}", cfg.final_font_path)
    else:
        canvas = _overlay_single_frame(canvas, frame_result, cfg)

    save_png(canvas, realtime_canvas_path(cfg, frame_idx))


def render_realtime_global(
    frame_idx: int,
    state: RealtimeState,
    color_frames: np.ndarray,
    is_warmup: bool,
    warmup_total: int,
    cfg: VisualizationConfig,
    excursion_cfg: ExcursionConfig,
) -> None:
    """累積拼接 track：frame[1..i] color 右尾拼接 canvas + 全局 overlay（或狀態文字）。"""
    if not should_save_realtime(cfg):
        return

    stride = state.stride_pixel
    tails = [
        color_frames[k][:, -stride:]
        for k in range(1, state.last_frame_idx + 1)
    ]
    canvas = np.concatenate(tails, axis=1)

    if is_warmup:
        canvas = _draw_status_text(
            canvas, f"warming up {frame_idx}/{warmup_total}", cfg.final_font_path)
    elif state.excursion is None:
        canvas = _draw_status_text(canvas, "computing...", cfg.final_font_path)
    else:
        canvas = _overlay_global(canvas, state, cfg)

    save_png(canvas, realtime_global_path(cfg, frame_idx))


# ---------- overlay helpers ----------

def _overlay_single_frame(canvas, frame_result, cfg):
    """單 frame overlay（同 LEGACY final）：motion curve 軌跡 + markers + 文字。"""
    if cfg.final_show_motion_curve:
        for x, y in enumerate(frame_result.motion_curve.init_diaphragm):
            cv2.circle(canvas, (int(x), int(y)), radius=1,
                       color=_FINAL_MOTION_COLOR, thickness=-1)

    wants_markers = cfg.final_show_peak_markers
    wants_text = cfg.final_show_excursion_text
    if frame_result.measurements and (wants_markers or wants_text):
        canvas = excursion_info_display(
            figure=canvas,
            measurements=frame_result.measurements,
            font_path=cfg.final_font_path,
            peak='ct' if wants_markers else '',
            show_text=wants_text,
        )
    return canvas


def _overlay_global(canvas, state: RealtimeState, cfg):
    """全局 overlay：累積 stitched motion curve 軌跡 + markers + 文字。"""
    if cfg.final_show_motion_curve:
        for x, y in enumerate(state.stitched_init_diaphragm):
            cv2.circle(canvas, (int(x), int(y)), radius=1,
                       color=_FINAL_MOTION_COLOR, thickness=-1)

    wants_markers = cfg.final_show_peak_markers
    wants_text = cfg.final_show_excursion_text
    if state.measurements and (wants_markers or wants_text):
        canvas = excursion_info_display(
            figure=canvas,
            measurements=state.measurements,
            font_path=cfg.final_font_path,
            peak='ct' if wants_markers else '',
            show_text=wants_text,
        )
    return canvas


def _draw_status_text(figure: np.ndarray, text: str, font_path: str) -> np.ndarray:
    """置中上方畫狀態文字（warming up / computing）；白字黑 stroke，ratio 化。"""
    h, w = figure.shape[:2]
    font_size = max(1, round(_RATIO_STATUS_FONT * h))
    stroke_w = max(1, round(_RATIO_STATUS_STROKE * h))

    img_pil = Image.fromarray(cv2.cvtColor(figure, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(font_path, font_size)

    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    tw = bbox[2] - bbox[0]
    tx = max(0, (w - tw) // 2)
    ty = round(h * _RATIO_STATUS_TOP)
    draw.text(
        (tx, ty), text, font=font,
        fill=_STATUS_TEXT_COLOR,
        stroke_width=stroke_w,
        stroke_fill=_STATUS_STROKE_FILL,
    )
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
