"""Visualization 層設定。

`enabled` 為總開關（False → 全 track 零 I/O）。其下各 track 各自 save_* 旗標 gate：

| Track | save 旗標 | 路徑 | 生效 mode | 渲染者 |
|---|---|---|---|---|
| final          | `save_final`               | `output/final/{i:04d}.png`                  | 全部 | PipelineVisualizer.render_frame |
| debug          | `save_debug`               | `output/debug/{stage}/{i:04d}.png`          | 全部 | PipelineVisualizer.render_frame |
| realtime video | `save_realtime_video`      | `output/realtime/{stem}_realtime.mp4`       | 僅 REALTIME | RealtimeVideoWriter |
| realtime PNG   | `save_realtime_canvas_png` | `output/realtime/canvas/{i:04d}.png`        | 僅 REALTIME | render_realtime_canvas + cv2.imwrite |

track × mode 重點：
  - final / debug 經 `_run_single_frame` → 所有 mode（含 REALTIME heavy 幀）都會產出
  - realtime video / PNG 只有 REALTIME mode 會呼叫 renderer；其他 mode 設 True 無效果
  - REALTIME 預設 `save_realtime_video=True`、`save_realtime_canvas_png=False`：
    一般使用拿 mp4 即可；單幀 debug 才開 PNG（檔名稀疏、跳號正常）

元素開關分組：
  - final_show_*：gate final track 的元素
  - rt_show_*   ：gate realtime canvas 內容（**video 與 PNG 共用同一張 canvas array**，
                  rt_show_* 同時影響兩種輸出）

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

    # REALTIME mode mp4 影片輸出（預設開，使用者一般拿這個成品）
    save_realtime_video: bool = True
    # REALTIME mode 每幀 canvas PNG（debug 用，預設關；檔名稀疏跳號正常）
    save_realtime_canvas_png: bool = False

    # None = 全部已知 stage；set = 只存這幾個（名稱見 visualization.stages）
    debug_stages: Optional[FrozenSet[str]] = None

    # Final overlay 文字字體（excursion_info_display 用，PIL 載入；final / realtime 共用）
    final_font_path: str = "./font/Altinn-DIN Bold.otf"

    # final track 元素開關（enabled=True + save_final=True 時生效）
    final_show_motion_curve: bool = False       # motion curve 啞黃軌跡（debug 用，覆在底圖上）
    final_show_peak_markers: bool = True       # crest/trough 圓點 + 虛線 + 標籤
    final_show_excursion_text: bool = True     # excursion_cm / sec / velocity 自訂字型文字

    # realtime canvas 元素開關（video 與 PNG 共用同一張 canvas array，rt_show_* 同時影響兩種輸出）
    rt_show_motion_curve: bool = True          # 即時軌跡是 realtime 主視覺，預設開
    rt_show_peak_markers: bool = True          # crest/trough markers
    rt_show_excursion_text: bool = True        # excursion_cm 文字
