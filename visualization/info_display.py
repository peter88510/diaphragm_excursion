"""Final overlay 文字標註與點位繪製。

對外入口：excursion_info_display(figure, peaks_info, font_path, peak='ct')

  figure       : BGR canvas（會被改寫且回傳）
  peaks_info   : legacy dict 格式 {idx: {trough, crest, velocity, excursion, time_sec}}
                  目前只取 select_idx=0；未來 multi-batch 視覺化擴充時再改
  font_path    : TrueType / OpenType 字體（PIL 載入）
  peak         : 'c' / 't' / 'ct' — 控制要畫哪些 marker / 文字

從原 root excursion_rule.py 的 excursion_info_display 搬出並重構：
  - 修 bug：label 位置原本以 `label == "Crest"` 字串比對決定上下，但實際 label 是
    "Highest (end-inspiratory)" → 改用明確的 label_above 旗標
  - 修 bug：getTextSize 量兩次（scale 0.6 vs 0.8）造成邊界檢查與底框尺寸不一致 → 統一 0.8
  - 視覺常數抽到 module top（顏色 / 尺寸 / 字型）
  - peaks_info 用 named key 存取，不依靠 dict 插入順序
  - 三次 PIL 文字繪製合併成單次 BGR↔PIL 轉換
  - 加 None guard（excursion_cm 可能為 None）
  - 加 type hints + 移除註解掉的 dead code
"""
from typing import Dict, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ----- Marker（cv2 標籤）-----
_CREST_COLOR = (0, 255, 255)        # 黃，波峰
_TROUGH_COLOR = (255, 128, 0)       # 橘，波谷
_DOT_RADIUS = 2
_BAR_LENGTH = 50                     # 垂直虛線長度
_DASH_STEP = 8                       # dash + gap pitch
_DASH_LEN = 4                        # dash 本身長度

_LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
_LABEL_SCALE = 0.8
_LABEL_THICK = 2
_LABEL_BG_COLOR = (40, 40, 40)
_LABEL_TEXT_COLOR = (255, 255, 255)
_LABEL_BG_ALPHA = 0.6

# ----- 大文字（PIL 自訂字體）-----
_BIG_FONT_SIZE = 36
_BIG_TEXT_COLOR = (255, 255, 255)
_BIG_STROKE_W = 2
_BIG_STROKE_FILL = (0, 0, 0)


def excursion_info_display(
    figure: np.ndarray,
    peaks_info: Dict,
    font_path: str = "./font/Altinn-DIN Bold.otf",
    peak: str = 'ct',
    show_text: bool = True,
) -> np.ndarray:
    """在 figure 上加 crest / trough markers 與 excursion / time / velocity 文字。

    Args:
        peak: marker 選擇 — 'c' 只波峰、't' 只波谷、'ct' 兩個、'' 都不畫
        show_text: 是否畫大文字（excursion / time / velocity）
    """
    info = peaks_info[0]
    trough = info["trough"]
    crest = info["crest"]
    excursion_cm = info["excursion"]
    time_sec = info["time_sec"]
    velocity = info["velocity"]

    if peak in ('c', 'ct'):
        figure = _draw_peak_marker(
            figure,
            (crest["x"], crest["y"]),
            "Highest (end-inspiratory)",
            _CREST_COLOR,
            label_above=True,
        )
    if peak in ('t', 'ct'):
        figure = _draw_peak_marker(
            figure,
            (trough["x"], trough["y"]),
            "Lowest (end-expiration)",
            _TROUGH_COLOR,
            label_above=False,
        )

    if show_text:
        figure = _draw_big_text_block(
            figure, font_path,
            excursion_cm=excursion_cm,
            time_sec=time_sec,
            velocity=velocity,
        )
    return figure


def _draw_peak_marker(
    img: np.ndarray,
    point: Tuple[int, int],
    label: str,
    color: Tuple[int, int, int],
    label_above: bool,
) -> np.ndarray:
    """畫實心圓點 + 垂直虛線 + 半透明底框標籤。"""
    h, w = img.shape[:2]
    x, y = int(point[0]), int(point[1])

    # 圓點
    cv2.circle(img, (x, y), radius=_DOT_RADIUS, color=color, thickness=-1)

    # 垂直虛線（dash + gap）
    for i in range(0, _BAR_LENGTH, _DASH_STEP):
        cv2.line(img, (x, y + i), (x, y + i + _DASH_LEN), color, 1)

    # 文字位置（label_above 決定在 marker 上方還下方）
    (tw, th), _ = cv2.getTextSize(label, _LABEL_FONT, _LABEL_SCALE, _LABEL_THICK)
    tx = x + 10
    ty = y - 10 if label_above else y + _BAR_LENGTH + 20

    # 邊界調整
    if tx + tw + 10 > w:
        tx = w - tw - 10
    if ty - th < 0:
        ty = th + 10
    if ty + 5 > h:
        ty = h - 10

    # 半透明底框
    overlay = img.copy()
    cv2.rectangle(
        overlay,
        (tx - 5, ty - th - 5),
        (tx + tw + 5, ty + 5),
        _LABEL_BG_COLOR, -1,
    )
    img = cv2.addWeighted(overlay, _LABEL_BG_ALPHA, img, 1 - _LABEL_BG_ALPHA, 0)

    # 文字
    cv2.putText(
        img, label, (tx, ty),
        _LABEL_FONT, _LABEL_SCALE,
        _LABEL_TEXT_COLOR, _LABEL_THICK, cv2.LINE_AA,
    )
    return img


def _draw_big_text_block(
    img: np.ndarray,
    font_path: str,
    excursion_cm,
    time_sec,
    velocity,
) -> np.ndarray:
    """用 PIL 自訂字型寫 excursion / time / velocity（單次 BGR↔PIL 轉換）。"""
    h, w = img.shape[:2]
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    font = ImageFont.truetype(font_path, _BIG_FONT_SIZE)

    def write(text: str, position: Tuple[int, int]) -> None:
        draw.text(
            position, text, font=font,
            fill=_BIG_TEXT_COLOR,
            stroke_width=_BIG_STROKE_W,
            stroke_fill=_BIG_STROKE_FILL,
        )

    if excursion_cm is not None:
        write(f"{excursion_cm} cm", (100, 50))

    if velocity is not None and time_sec is not None:
        write(f"{time_sec} sec", (w - 300, h - 140))
        write(f"v = {velocity}", (w - 300, h - 80))

    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
