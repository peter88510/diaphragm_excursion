"""REALTIME mode 雙 track viz。

兩 track 皆從 RealtimeState 累積拼接結果衍生（同源 overlay）：
  - global track：完整累積 color canvas（frame 各取右尾 shift 拼接）+ 全局 overlay
                  → {output_dir}/realtime/global/{i:04d}.png
  - canvas track：base = frame[i] 原始影像（恆 = 影像寬），疊上 global 軌跡最右段
                  （右錨定對齊：global 最新點 = frame[i] 最右欄）
                  → {output_dir}/realtime/canvas/{i:04d}.png
                  模擬即時監視器：邊拍邊看新進來的計算結果，固定寬不裁切。

對齊原理：M-mode x 軸為時間，frame[i] 與 global 最右段都代表「最近這段時間」，
逐欄對應同一時刻（frame[i]→[i+1] 捲動量 = estimate_shift；估計準時無偏移）。
canvas 比 global 窄時取 global 最右 (= 影像寬) 段；global 尚短時右錨定、左側留白。

累積邊界虛線（canvas track）：line_x = view_width - full_width，標記左側起始未計算 /
右側已累積；隨累積往左捲，full_width >= view_width 後 line_x<=0 即不畫。global track
canvas=全寬 → line_x=0 不畫。

元素開關讀 cfg.rt_show_*（motion_curve / peak_markers / excursion_text）。

Warmup gating（is_warmup 由 main 判定 frame_idx <= warmup_frames）：
  - warmup 期 → "warming up i/N"；過 warmup 但 width 未達 min（excursion=None）→ "computing..."
  - status 文字置左上（固定寬不裁切）；虛線各狀態都疊（呈現累積進度）

px / 字型 ratio 化沿用 info_display（ref height-relative）；status 文字 ratio 同基準。
"""
from dataclasses import replace

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


# status 文字（ref 1500×955；以 image height 為基準）；置左上
_REF_HEIGHT = 955
_RATIO_STATUS_FONT = 28 / _REF_HEIGHT
_RATIO_STATUS_STROKE = 2 / _REF_HEIGHT
_RATIO_STATUS_LEFT = 0.03
_RATIO_STATUS_TOP = 0.05
_STATUS_TEXT_COLOR = (255, 255, 255)
_STATUS_STROKE_FILL = (0, 0, 0)

# 累積邊界虛線（canvas track）：左側=起始未計算、右側=已累積；洋紅、y 方向虛線
_BOUNDARY_COLOR = (255, 0, 255)   # magenta BGR
_RATIO_BOUNDARY_DASH = 6 / _REF_HEIGHT


def render_realtime_global(
    frame_idx: int,
    state: RealtimeState,
    color_frames: np.ndarray,
    is_warmup: bool,
    warmup_total: int,
    cfg: VisualizationConfig,
    excursion_cfg: ExcursionConfig,
) -> None:
    """完整累積拼接 track：global color canvas + 全局 overlay（或狀態文字）。"""
    if not should_save_realtime(cfg) or not state.ingested_indices:
        return

    canvas = _build_global_color_canvas(state, color_frames)
    canvas = _annotate(canvas, state, frame_idx, is_warmup, warmup_total, cfg)
    save_png(canvas, realtime_global_path(cfg, frame_idx))


def render_realtime_canvas(
    frame_idx: int,
    image_color: np.ndarray,
    state: RealtimeState,
    is_warmup: bool,
    warmup_total: int,
    cfg: VisualizationConfig,
    excursion_cfg: ExcursionConfig,
) -> None:
    """即時監視器 track：base = frame[i] 原始影像，疊 global 軌跡最右段（右錨定）。"""
    if not should_save_realtime(cfg) or not state.ingested_indices:
        return

    canvas = image_color.copy()        # base = frame[i]，寬 = 影像寬（不寫死）
    canvas = _annotate(canvas, state, frame_idx, is_warmup, warmup_total, cfg)
    save_png(canvas, realtime_canvas_path(cfg, frame_idx))


# ---------- shared helpers ----------

def _build_global_color_canvas(
    state: RealtimeState, color_frames: np.ndarray,
) -> np.ndarray:
    """每個 ingested frame 取 color 右尾 = 該幀實測 shift，concat 成累積 color canvas。"""
    tails = [
        color_frames[idx][:, -shift:]
        for idx, shift in zip(state.ingested_indices, state.shifts)
    ]
    return np.concatenate(tails, axis=1)


def _annotate(
    canvas: np.ndarray,
    state: RealtimeState,
    frame_idx: int,
    is_warmup: bool,
    warmup_total: int,
    cfg: VisualizationConfig,
) -> np.ndarray:
    """依狀態畫 overlay 或 status 文字，最後疊累積邊界虛線。"""
    if is_warmup:
        canvas = _draw_status_text(
            canvas, f"warming up {frame_idx}/{warmup_total}", cfg.final_font_path)
    elif state.excursion is None:
        canvas = _draw_status_text(canvas, "computing...", cfg.final_font_path)
    else:
        canvas = _overlay(canvas, state, cfg)

    # 累積邊界虛線：line_x = 累積區左界。canvas track 才 > 0；
    # global track（canvas=全寬）line_x=0、累積滿視窗後 line_x<=0 → 不畫（捲出）
    line_x = canvas.shape[1] - state.full_width
    if line_x > 0:
        _draw_boundary_line(canvas, line_x)
    return canvas


def _overlay(canvas: np.ndarray, state: RealtimeState, cfg):
    """疊 global stitched 軌跡 + markers；canvas 比 global 窄時取最右段右錨定對齊。

    offset = global signal x → canvas x 的平移量 = full_width - canvas_width：
      - global track（canvas = 全寬）→ offset 0，畫全段
      - canvas track（canvas = 影像寬）→ offset = full - view，畫最右段（右錨定）
      - global 尚短於影像寬時 offset < 0，全段右錨定、左側留白
    """
    view_width = canvas.shape[1]
    offset = state.full_width - view_width

    if cfg.rt_show_motion_curve:
        sig = state.stitched_init_diaphragm
        for gx in range(max(0, offset), state.full_width):
            cv2.circle(canvas, (gx - offset, int(sig[gx])), radius=1,
                       color=_FINAL_MOTION_COLOR, thickness=-1)

    wants_markers = cfg.rt_show_peak_markers
    wants_text = cfg.rt_show_excursion_text
    if state.measurements and (wants_markers or wants_text):
        ms = state.measurements if offset == 0 else _offset_measurements(
            state.measurements, offset, view_width)
        canvas = excursion_info_display(
            figure=canvas,
            measurements=ms,
            font_path=cfg.final_font_path,
            peak='ct' if wants_markers else '',
            show_text=wants_text,
        )
    return canvas


def _draw_boundary_line(canvas: np.ndarray, x: int) -> None:
    """在 x 處畫 y 方向洋紅虛線（累積區左界）；隨累積往左移、捲出視窗即不畫。"""
    h = canvas.shape[0]
    dash = max(2, round(_RATIO_BOUNDARY_DASH * h))
    step = dash * 2
    for y in range(0, h, step):
        cv2.line(canvas, (x, y), (x, min(y + dash, h - 1)), _BOUNDARY_COLOR, 1)


def _offset_measurements(measurements, offset: int, width: int):
    """把 crest/trough x 平移 -offset；整組 x 都落在視窗外（左<0 或右≥width）者丟棄。"""
    out = []
    for m in measurements:
        cx = m.crest[0] - offset
        tx = m.trough[0] - offset
        if (cx < 0 and tx < 0) or (cx >= width and tx >= width):
            continue
        out.append(replace(m, crest=(cx, m.crest[1]), trough=(tx, m.trough[1])))
    return out


def _draw_status_text(figure: np.ndarray, text: str, font_path: str) -> np.ndarray:
    """左上角畫狀態文字（warming up / computing）；白字黑 stroke，ratio 化。"""
    h, w = figure.shape[:2]
    font_size = max(1, round(_RATIO_STATUS_FONT * h))
    stroke_w = max(1, round(_RATIO_STATUS_STROKE * h))

    img_pil = Image.fromarray(cv2.cvtColor(figure, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(font_path, font_size)

    tx = round(w * _RATIO_STATUS_LEFT)
    ty = round(h * _RATIO_STATUS_TOP)
    draw.text(
        (tx, ty), text, font=font,
        fill=_STATUS_TEXT_COLOR,
        stroke_width=stroke_w,
        stroke_fill=_STATUS_STROKE_FILL,
    )
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
