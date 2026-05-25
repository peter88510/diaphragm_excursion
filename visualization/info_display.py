"""Final overlay 文字標註與點位繪製。

對外入口：excursion_info_display(figure, measurements, font_path, peak='ct')

  figure       : BGR canvas（會被改寫且回傳）
  measurements : List[PeakInfo]
                  - markers：每組 crest/trough 都會畫上去
                  - big text：透過 aggregate_measurements 取單一代表性 PeakInfo
  font_path    : TrueType / OpenType 字體（PIL 載入）
  peak         : 'c' / 't' / 'ct' / '' — 控制要畫哪些 marker

Patch 13C 重構：
  - 所有 px 常數改以 1500×955 為 ref，按 image height 比例縮放
  - 大文字塊吃 aggregate_measurements()（暫 fallback 第 0 組）
  - markers 改 for-loop 跑每組 PeakInfo（原本只畫第 0 組）
  - 簽名改吃 List[PeakInfo]（移除 legacy peaks_info dict 中介層）
"""
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from algorithm.excursion import PeakInfo, aggregate_measurements


# ref 解析度：所有 px / scale 常數以此 image height 為基準
_REF_HEIGHT = 955

# ----- Marker（cv2 標籤）-----
_CREST_COLOR = (0, 255, 255)        # 黃，波峰
_TROUGH_COLOR = (255, 128, 0)       # 橘，波谷
_RATIO_DOT_RADIUS = 2 / _REF_HEIGHT
_RATIO_BAR_LENGTH = 50 / _REF_HEIGHT
_RATIO_DASH_STEP = 8 / _REF_HEIGHT
_RATIO_DASH_LEN = 4 / _REF_HEIGHT

_LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
_RATIO_LABEL_SCALE = 0.8 / _REF_HEIGHT     # cv2 scale（× ref_h 還原 0.8）
_RATIO_LABEL_THICK = 2 / _REF_HEIGHT
_RATIO_LABEL_OFFSET = 10 / _REF_HEIGHT     # label 文字相對 marker 偏移
_RATIO_LABEL_PAD = 5 / _REF_HEIGHT         # 半透明底框 padding
_LABEL_BG_COLOR = (40, 40, 40)
_LABEL_TEXT_COLOR = (255, 255, 255)
_LABEL_BG_ALPHA = 0.6

# ----- 大文字（PIL 自訂字體）-----
_RATIO_BIG_FONT = 36 / _REF_HEIGHT
_RATIO_BIG_STROKE = 2 / _REF_HEIGHT
_BIG_TEXT_COLOR = (255, 255, 255)
_BIG_STROKE_FILL = (0, 0, 0)
# big text 位置 ratio（ref 下對應 (100, 50) / (w-300, h-140) / (w-300, h-80)）
_RATIO_BIG_TL = (100 / _REF_HEIGHT, 50 / _REF_HEIGHT)
_RATIO_BIG_BR_TIME = (300 / _REF_HEIGHT, 140 / _REF_HEIGHT)
_RATIO_BIG_BR_VELOCITY = (300 / _REF_HEIGHT, 80 / _REF_HEIGHT)


def _px(ratio: float, ref_h: int) -> int:
    """ratio × ref_h → int pixel；最小回 1（避免 0 半徑）。"""
    return max(1, round(ratio * ref_h))


def excursion_info_display(
    figure: np.ndarray,
    measurements: List[PeakInfo],
    font_path: str = "./font/Altinn-DIN Bold.otf",
    peak: str = 'ct',
    show_text: bool = True,
) -> np.ndarray:
    """在 figure 上加 crest / trough markers 與 excursion / time / velocity 文字。

    Args:
        measurements: List[PeakInfo]；markers 每組都畫，文字塊透過
            `aggregate_measurements` 取單一 PeakInfo（暫 fallback 第 0 組）
        peak: marker 選擇 — 'c' 只波峰、't' 只波谷、'ct' 兩個、'' 都不畫
        show_text: 是否畫大文字（excursion / time / velocity）
    """
    if not measurements:
        return figure

    ref_h = figure.shape[0]

    for m in measurements:
        if peak in ('c', 'ct'):
            figure = _draw_peak_marker(
                figure, ref_h,
                (m.crest[0], m.crest[1]),
                "Highest (end-inspiratory)",
                _CREST_COLOR,
                label_above=True,
            )
        if peak in ('t', 'ct'):
            figure = _draw_peak_marker(
                figure, ref_h,
                (m.trough[0], m.trough[1]),
                "Lowest (end-expiration)",
                _TROUGH_COLOR,
                label_above=False,
            )

    if show_text:
        agg = aggregate_measurements(measurements)
        if agg is not None:
            figure = _draw_big_text_block(
                figure, ref_h, font_path,
                excursion_cm=agg.excursion_cm,
                time_sec=agg.time_sec,
                velocity=agg.velocity,
            )
    return figure


def _draw_peak_marker(
    img: np.ndarray,
    ref_h: int,
    point: Tuple[int, int],
    label: str,
    color: Tuple[int, int, int],
    label_above: bool,
) -> np.ndarray:
    """畫實心圓點 + 垂直虛線 + 半透明底框標籤。"""
    h, w = img.shape[:2]
    x, y = int(point[0]), int(point[1])

    dot_r = _px(_RATIO_DOT_RADIUS, ref_h)
    bar_len = _px(_RATIO_BAR_LENGTH, ref_h)
    dash_step = _px(_RATIO_DASH_STEP, ref_h)
    dash_len = _px(_RATIO_DASH_LEN, ref_h)
    scale = _RATIO_LABEL_SCALE * ref_h
    thick = _px(_RATIO_LABEL_THICK, ref_h)
    offset = _px(_RATIO_LABEL_OFFSET, ref_h)
    pad = _px(_RATIO_LABEL_PAD, ref_h)

    # 圓點
    cv2.circle(img, (x, y), radius=dot_r, color=color, thickness=-1)

    # 垂直虛線（dash + gap）
    for i in range(0, bar_len, dash_step):
        cv2.line(img, (x, y + i), (x, y + i + dash_len), color, 1)

    # 文字位置（label_above 決定在 marker 上方還下方）
    (tw, th), _ = cv2.getTextSize(label, _LABEL_FONT, scale, thick)
    tx = x + offset
    ty = y - offset if label_above else y + bar_len + offset * 2

    # 邊界調整（保留原版 mixed offset/pad 語義）
    if tx + tw + offset > w:
        tx = w - tw - offset
    if ty - th < 0:
        ty = th + offset
    if ty + pad > h:
        ty = h - offset

    # 半透明底框
    overlay = img.copy()
    cv2.rectangle(
        overlay,
        (tx - pad, ty - th - pad),
        (tx + tw + pad, ty + pad),
        _LABEL_BG_COLOR, -1,
    )
    img = cv2.addWeighted(overlay, _LABEL_BG_ALPHA, img, 1 - _LABEL_BG_ALPHA, 0)

    # 文字
    cv2.putText(
        img, label, (tx, ty),
        _LABEL_FONT, scale,
        _LABEL_TEXT_COLOR, thick, cv2.LINE_AA,
    )
    return img


def _draw_big_text_block(
    img: np.ndarray,
    ref_h: int,
    font_path: str,
    excursion_cm,
    time_sec,
    velocity,
) -> np.ndarray:
    """用 PIL 自訂字型寫 excursion / time / velocity（單次 BGR↔PIL 轉換）。"""
    h, w = img.shape[:2]
    font_size = _px(_RATIO_BIG_FONT, ref_h)
    stroke_w = _px(_RATIO_BIG_STROKE, ref_h)

    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(font_path, font_size)

    def write(text: str, position: Tuple[int, int]) -> None:
        draw.text(
            position, text, font=font,
            fill=_BIG_TEXT_COLOR,
            stroke_width=stroke_w,
            stroke_fill=_BIG_STROKE_FILL,
        )

    tl_x = _px(_RATIO_BIG_TL[0], ref_h)
    tl_y = _px(_RATIO_BIG_TL[1], ref_h)
    br_time_dx = _px(_RATIO_BIG_BR_TIME[0], ref_h)
    br_time_dy = _px(_RATIO_BIG_BR_TIME[1], ref_h)
    br_vel_dx = _px(_RATIO_BIG_BR_VELOCITY[0], ref_h)
    br_vel_dy = _px(_RATIO_BIG_BR_VELOCITY[1], ref_h)

    if excursion_cm is not None:
        write(f"{excursion_cm} cm", (tl_x, tl_y))

    if velocity is not None and time_sec is not None:
        write(f"{time_sec} sec", (w - br_time_dx, h - br_time_dy))
        write(f"v = {velocity}", (w - br_vel_dx, h - br_vel_dy))

    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
