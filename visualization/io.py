"""Viz 存檔工具。

統一路徑規則：
  final  → {output_dir}/final/{i:04d}.png
  debug  → {output_dir}/debug/{stage}/{i:04d}.png

image 一律為 cv2 BGR uint8 ndarray（顏色空間由各 layer 自己負責）。

should_save_* helper 在呼叫端先 gate，避免 layer 做完渲染才發現用不到。
"""
from pathlib import Path

import cv2
import numpy as np

from config.visualization_config import VisualizationConfig
from visualization.stages import ALL_STAGES


def final_path(cfg: VisualizationConfig, frame_idx: int) -> Path:
    return cfg.output_dir / "final" / f"{frame_idx:04d}.png"


def global_final_path(cfg: VisualizationConfig) -> Path:
    """GLOBAL_WINDOW mode 的全局 final overlay；單一檔不帶 frame_idx。"""
    return cfg.output_dir / "global" / "final.png"


def realtime_canvas_path(cfg: VisualizationConfig, frame_idx: int) -> Path:
    """REALTIME mode canvas track PNG（逐 frame，debug 用；預設不開）。"""
    return cfg.output_dir / "realtime" / "canvas" / f"{frame_idx:04d}.png"


def realtime_video_path(cfg: VisualizationConfig, source_path: str) -> Path:
    """REALTIME mode 的 mp4 影片輸出；命名 `{source_stem}_realtime.mp4`。"""
    stem = Path(source_path).stem
    return cfg.output_dir / "realtime" / f"{stem}_realtime.mp4"


def debug_path(cfg: VisualizationConfig, stage: str, frame_idx: int) -> Path:
    # stage 是內部常數，但會落到檔案系統 — 做基本 sanitize 防意外字元（CLAUDE.md §9）
    safe = stage.replace("_", "").replace("-", "")
    if not safe.isalnum():
        raise ValueError(f"stage name 必須只含 alnum/_/-: got {stage!r}")
    return cfg.output_dir / "debug" / stage / f"{frame_idx:04d}.png"


def should_save_final(cfg: VisualizationConfig) -> bool:
    return cfg.enabled and cfg.save_final


def should_save_realtime_video(cfg: VisualizationConfig) -> bool:
    return cfg.enabled and cfg.save_realtime_video


def should_save_realtime_canvas_png(cfg: VisualizationConfig) -> bool:
    return cfg.enabled and cfg.save_realtime_canvas_png


def should_save_debug(cfg: VisualizationConfig, stage: str) -> bool:
    """是否要為此 stage 落 debug 圖。

    未知 stage 名直接 raise（catch 拼字錯誤）；
    debug_stages=None 視為 ALL_STAGES。
    """
    if stage not in ALL_STAGES:
        raise ValueError(
            f"unknown debug stage {stage!r}; 請先在 visualization.stages 註冊"
        )
    if not (cfg.enabled and cfg.save_debug):
        return False
    if cfg.debug_stages is None:
        return True
    return stage in cfg.debug_stages


def save_png(image: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), image)
    if not ok:
        raise IOError(f"cv2.imwrite failed: {path}")
