"""個人 run 參數入口（模板）。

使用：複製本檔為 run_config.py（已 gitignore），填入 IMAGE_PATH 並依需求
override。所有 per-run 可調項集中在此 —— image_path + RunBundle overrides。

設計原則：
- 各模組 dataclass canonical default 不在此改動；只在這裡 override 你要的值
- main.py 只留穩定 orchestration，個人實驗值不進 commit
"""
from config import Phase, RunBundle
from config.multiframe_config import MultiframeMode

# 你的 DICOM 路徑（機器相關，不入 git）
IMAGE_PATH = r"<填入你的 DICOM 路徑>"


def build_bundle() -> RunBundle:
    """建立 RunBundle 並 override 個人實驗值。"""
    bundle = RunBundle.for_phase(Phase.EXCURSION)

    # ↓ 在這裡 override 你要的實驗值（範例，視需求開啟）
    # bundle.multiframe.mode = MultiframeMode.REALTIME
    # bundle.multiframe.keyframe_indices = [86, 149]
    # bundle.viz.enabled = True
    # bundle.viz.save_realtime = True

    return bundle
