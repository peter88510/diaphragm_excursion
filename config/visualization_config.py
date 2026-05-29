"""Visualization 層設定。

`enabled` 為總開關（False → 全 track 零 I/O）。其下三個獨立 track，各自一個
save_* 旗標 gate，輸出到不同目錄，可任意組合：

| Track | save 旗標 | 路徑 | 生效 mode | 渲染者 |
|---|---|---|---|---|
| final   | `save_final`    | `output/final/{i:04d}.png`        | 全部 | PipelineVisualizer.render_frame |
| debug   | `save_debug`    | `output/debug/{stage}/{i:04d}.png`| 全部 | PipelineVisualizer.render_frame |
| realtime| `save_realtime` | `output/realtime/{canvas,global}/`| 僅 REALTIME | render_realtime_* |

track × mode 重點：
  - final / debug 經 `_run_single_frame` → 所有 mode（含 REALTIME）都會產出
  - realtime 只有 REALTIME mode 會呼叫 renderer；其他 mode 設 save_realtime=True 無效果
  - 三 track 獨立、不強制互斥：REALTIME 通常只開 save_realtime（把 save_final/
    save_debug 設 False 避免重複 final/ 輸出），但要 debug 各 stage 時仍可手動開 save_debug

元素開關分組：
  - final_show_*：gate final track 的元素
  - rt_show_*   ：gate realtime track（canvas + global）的元素

stage 過濾（debug track）：
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

    # REALTIME mode 專屬 track（canvas + global 雙輸出；enabled=True 時才生效）
    save_realtime: bool = False

    # None = 全部已知 stage；set = 只存這幾個（名稱見 visualization.stages）
    debug_stages: Optional[FrozenSet[str]] = None

    # Final overlay 文字字體（excursion_info_display 用，PIL 載入；final / realtime 共用）
    final_font_path: str = "./font/Altinn-DIN Bold.otf"

    # final track 元素開關（enabled=True + save_final=True 時生效）
    final_show_motion_curve: bool = False       # motion curve 啞黃軌跡（debug 用，覆在底圖上）
    final_show_peak_markers: bool = True       # crest/trough 圓點 + 虛線 + 標籤
    final_show_excursion_text: bool = True     # excursion_cm / sec / velocity 自訂字型文字

    # realtime track 元素開關（enabled=True + save_realtime=True 時生效）
    rt_show_motion_curve: bool = True          # 即時軌跡是 realtime 主視覺，預設開
    rt_show_peak_markers: bool = True          # crest/trough markers
    rt_show_excursion_text: bool = True        # excursion_cm 文字
