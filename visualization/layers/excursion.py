"""Excursion brightness 波形 debug 圖。

對應原 brightness.py L80-90 的 plt 段：
  - 橙線：diaphragm_p_4trough 波形
  - 紅星：crest (find_peaks on diaphragm_p_4crest)
  - 藍星：trough (find_peaks on -diaphragm_p_4trough)

實作：用 Figure + FigureCanvasAgg 避免動到 matplotlib 全域 backend
（原 module-level `matplotlib.use('TkAgg')` 已在 Patch 7 移除，本檔不要再讓它回來）。
"""
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from scipy.signal import find_peaks

from config import ExcursionConfig
from config.visualization_config import VisualizationConfig
from visualization import stages
from visualization.io import debug_path, should_save_debug


def render_excursion_brightness(
    diaphragm_p_4trough: np.ndarray,
    diaphragm_p_4crest: np.ndarray,
    excursion_config: ExcursionConfig,
    cfg: VisualizationConfig,
    frame_idx: int,
) -> None:
    """存 excursion 波形 + crest/trough 標記的 debug 圖。"""
    if not should_save_debug(cfg, stages.EXCURSION_BRIGHTNESS):
        return

    x_dim = len(diaphragm_p_4trough)
    distance = int(excursion_config.peak_min_distance_ratio * x_dim)
    prominence = excursion_config.peak_prominence
    crest, _ = find_peaks(diaphragm_p_4crest, distance=distance, prominence=prominence)
    troughs, _ = find_peaks(-diaphragm_p_4trough, distance=distance, prominence=prominence)

    fig = Figure(figsize=(8, 4))
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    ax.plot(diaphragm_p_4trough, color='orange')
    ax.plot(crest, diaphragm_p_4crest[crest], '*', color='red', label='crest')
    ax.plot(troughs, diaphragm_p_4trough[troughs], '*', label='trough')
    ax.set_title('[Excursion] Crest & Trough')
    ax.legend()
    fig.tight_layout()

    path = debug_path(cfg, stages.EXCURSION_BRIGHTNESS, frame_idx)
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.print_png(str(path))
