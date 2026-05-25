"""Visualization 層設定（Step 7）。

兩個獨立 track（互不混用，不會疊在同一張圖）：
  - final overlay：每 frame 一張綜合成果圖
      output/final/{i:04d}.png
  - debug images per stage：每個處理階段一張，檔名以 stage 區分
      output/debug/{stage}/{i:04d}.png

預設 enabled=False — production / 一般執行 zero side-effect。
要看 viz 才開，避免每 frame 落盤副作用。

stage 過濾：
  debug_stages=None  → enabled+save_debug 時，所有已知 stage 都存
  debug_stages={...} → 只存指定 stage（名稱見 visualization.stages）
"""
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Optional


@dataclass
class VisualizationConfig:
    enabled: bool = True
    output_dir: Path = Path("output")

    # 兩個獨立 track（enabled=True 時才生效）
    save_final: bool = True
    save_debug: bool = False

    # None = 全部已知 stage；set = 只存這幾個（名稱見 visualization.stages）
    debug_stages: Optional[FrozenSet[str]] = None

    # Final overlay 文字字體（excursion_info_display 用，PIL 載入）
    final_font_path: str = "./font/Altinn-DIN Bold.otf"

    # Final overlay 元素開關（enabled=True + save_final=True 時生效）
    final_show_motion_curve: bool = False       # motion curve 啞黃軌跡（debug 用，覆在底圖上）
    final_show_peak_markers: bool = True       # crest/trough 圓點 + 虛線 + 標籤
    final_show_excursion_text: bool = True     # excursion_cm / sec / velocity 自訂字型文字
