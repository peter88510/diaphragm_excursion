"""REALTIME mode (Mode 2) state + 累積拼接 + rolling excursion。

模擬醫生使用流程：探頭貼上 → 開始錄製 → 每幀新進 stride_pixel 訊號累積。

拼接策略（純右尾累積）：
  - frame[0] 為探頭啟動畫面，caller 跳過不 ingest
  - frame[1..N] 每幀只取右尾 stride_pixel（「新進」訊號）append 到 buffer
  - 累積 width = N × stride_pixel（N = 已 ingest 幀數）
  - frame[0] 與 frame[1] 為相鄰幀：frame[0] 左移 stride_pixel 移出左側、右側新進
    stride_pixel = frame[1]，故只取右尾即得「真正新進」段

Wavelet 邊界處理：
  - 純右尾 concat 會在每段邊界累積各 frame wavelet 的 edge artifact
  - 每 wavelet_refresh_every_n 幀對整段 buffer 重做 wavelet 消除（None = 不重做）

雙層門檻：
  - warmup_frames（UX gating）：由 viz 層使用，本檔不直接判
  - algorithm_min_width（algorithm 安全網）：累積 width < 此值跳過 brightness_way，
    避免 find_peaks / midline 在過短訊號出 garbage

streaming-ready：ingest_frame() 為外部接口；main.py 驅動 loop 逐幀呼叫，
未來接真實 stream 只需換來源，state 結構不變。
"""
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from algorithm.excursion import (
    ExcursionResult,
    PeakInfo,
    brightness_way,
    compute_peak_info,
)
from algorithm.frame_result import FrameResult
from algorithm.signal_processing import wavelet_denoising
from config.excursion_config import ExcursionConfig


@dataclass
class RealtimeState:
    # --- config snapshot（建構時帶入）---
    stride_pixel: int
    algorithm_min_width: int
    wavelet_refresh_every_n: Optional[int]
    wavelet_level_trough: int
    wavelet_level_crest: int

    # --- 累積 buffers（首次 ingest 前為 None；與 GlobalExcursionResult 對稱命名）---
    stitched_init_diaphragm: Optional[np.ndarray] = None     # (W_now,)
    stitched_smoothed_trough: Optional[np.ndarray] = None
    stitched_smoothed_crest: Optional[np.ndarray] = None
    stitched_p_trough: Optional[np.ndarray] = None
    stitched_p_crest: Optional[np.ndarray] = None
    stitched_diaphragm_mask: Optional[np.ndarray] = None     # (H, W_now)

    # --- rolling excursion（width < algorithm_min_width 時 None / []）---
    excursion: Optional[ExcursionResult] = None
    measurements: List[PeakInfo] = field(default_factory=list)

    # --- metadata ---
    last_frame_idx: int = -1
    n_ingested: int = 0
    last_wavelet_refresh_n: int = 0
    full_width: int = 0

    def ingest_frame(
        self,
        frame_result: FrameResult,
        idx: int,
        excursion_cfg: ExcursionConfig,
        scale_y: Optional[float] = None,
    ) -> None:
        """納入一個新 frame：append 右尾 → 視情況 refresh wavelet → rolling excursion。

        streaming-ready 外部接口；未來換真實 stream 來源只需照樣呼叫。
        """
        self._append_tail(frame_result)
        self.last_frame_idx = idx
        self.n_ingested += 1
        self.full_width = int(self.stitched_init_diaphragm.shape[0])

        if self._should_refresh_wavelet():
            self._refresh_wavelet()

        self._recompute_excursion(excursion_cfg, scale_y)

    # ---------- internal ----------

    def _append_tail(self, frame_result: FrameResult) -> None:
        """取 frame 的 motion_curve / mask 右尾 stride_pixel，初始化或 concat 到 buffer。"""
        mc = frame_result.motion_curve
        mask = frame_result.selection.diaphragm_mask
        s = self.stride_pixel

        init_t = mc.init_diaphragm[-s:]
        st_t = mc.smoothed_trough[-s:]
        sc_t = mc.smoothed_crest[-s:]
        pt_t = mc.diaphragm_p_trough[-s:]
        pc_t = mc.diaphragm_p_crest[-s:]
        mask_t = mask[:, -s:]

        if self.stitched_init_diaphragm is None:
            self.stitched_init_diaphragm = init_t.copy()
            self.stitched_smoothed_trough = st_t.copy()
            self.stitched_smoothed_crest = sc_t.copy()
            self.stitched_p_trough = pt_t.copy()
            self.stitched_p_crest = pc_t.copy()
            self.stitched_diaphragm_mask = mask_t.copy()
        else:
            self.stitched_init_diaphragm = np.concatenate(
                [self.stitched_init_diaphragm, init_t])
            self.stitched_smoothed_trough = np.concatenate(
                [self.stitched_smoothed_trough, st_t])
            self.stitched_smoothed_crest = np.concatenate(
                [self.stitched_smoothed_crest, sc_t])
            self.stitched_p_trough = np.concatenate(
                [self.stitched_p_trough, pt_t])
            self.stitched_p_crest = np.concatenate(
                [self.stitched_p_crest, pc_t])
            self.stitched_diaphragm_mask = np.concatenate(
                [self.stitched_diaphragm_mask, mask_t], axis=1)

    def _should_refresh_wavelet(self) -> bool:
        """每 wavelet_refresh_every_n 幀 refresh；未達 min_width / None 不 refresh。"""
        k = self.wavelet_refresh_every_n
        if k is None or self.full_width < self.algorithm_min_width:
            return False
        return (self.n_ingested - self.last_wavelet_refresh_n) >= k

    def _refresh_wavelet(self) -> None:
        """對整段累積 init_diaphragm 重做 wavelet → 更新 smoothed / p 信號（消邊界 artifact）。"""
        h = self.stitched_diaphragm_mask.shape[0]
        smoothed_trough = wavelet_denoising(
            self.stitched_init_diaphragm, level=self.wavelet_level_trough)
        smoothed_crest = wavelet_denoising(
            self.stitched_init_diaphragm, level=self.wavelet_level_crest)
        self.stitched_smoothed_trough = smoothed_trough
        self.stitched_smoothed_crest = smoothed_crest
        self.stitched_p_trough = np.round(h - smoothed_trough)
        self.stitched_p_crest = np.round(h - smoothed_crest)
        self.last_wavelet_refresh_n = self.n_ingested

    def _recompute_excursion(
        self,
        excursion_cfg: ExcursionConfig,
        scale_y: Optional[float],
    ) -> None:
        """累積 width 達門檻才跑全局 brightness_way；否則 excursion=None（cold-start guard）。"""
        if self.full_width < self.algorithm_min_width:
            self.excursion = None
            self.measurements = []
            return

        excursion = brightness_way(
            diaphragm_mask=self.stitched_diaphragm_mask,
            diaphragm_p_4crest=self.stitched_p_crest,
            diaphragm_p_4trough=self.stitched_p_trough,
            diaphragm_ori_y_value=self.stitched_init_diaphragm,
            config=excursion_cfg,
        )
        self.excursion = excursion
        self.measurements = [
            compute_peak_info(
                crest=batch.crest_position,
                trough=batch.trough_position,
                scale_y=scale_y,
            )
            for batch in excursion.batches
        ]
