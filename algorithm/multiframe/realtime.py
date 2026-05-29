"""REALTIME mode (Mode 2) state + 累積拼接 + rolling excursion。

模擬醫生使用流程：探頭貼上 → 開始錄製 → 每幀新進 stride_pixel 訊號累積。

拼接策略（純右尾累積 + 變動位移）：
  - frame[0] 為探頭啟動畫面，caller 跳過不 ingest
  - frame[i] 每幀取右尾 shift_px（caller 用 estimate_shift 算出的「新進」訊號量）
  - 累積 width = Σ shift_px（非固定；delay 幀 shift≈0 由 caller 跳過不 ingest）
  - shift_px 取代舊版固定 stride_pixel：實際超音波非理想 +8px，有 delay / 快進

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
from algorithm.motion_curve import MotionCurveResult
from algorithm.signal_processing import wavelet_denoising
from config.excursion_config import ExcursionConfig


@dataclass
class RealtimeState:
    # --- config snapshot（建構時帶入）---
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

    # --- 拼接紀錄（供 viz 對齊 color canvas；parallel lists）---
    ingested_indices: List[int] = field(default_factory=list)  # 每次 ingest 的 frame idx
    shifts: List[int] = field(default_factory=list)            # 對應每次取的右尾 px

    # --- metadata ---
    last_frame_idx: int = -1
    n_ingested: int = 0
    last_wavelet_refresh_n: int = 0
    full_width: int = 0

    def ingest_frame(
        self,
        motion_curve: MotionCurveResult,
        idx: int,
        shift_px: int,
        excursion_cfg: ExcursionConfig,
        scale_y: Optional[float] = None,
        full_mask: Optional[np.ndarray] = None,
    ) -> None:
        """納入一個新 frame：append 右尾 → 視情況 refresh wavelet → rolling excursion。

        分層 cadence（Patch 19）：light 幀只帶 motion_curve；heavy 幀另帶 paddle
        整張 frame mask（full_mask）。curve buffer 永遠 append-only；mask buffer
        light 沿用最右欄、heavy 以 full_mask 右對齊覆蓋最右段（refresh-recent）。
        streaming-ready 接口；shift_px 由 caller 用 estimate_shift 算出。
        """
        self._append_tail(motion_curve, shift_px, full_mask)
        self.ingested_indices.append(idx)
        self.shifts.append(shift_px)
        self.last_frame_idx = idx
        self.n_ingested += 1
        self.full_width = int(self.stitched_init_diaphragm.shape[0])

        if self._should_refresh_wavelet():
            self._refresh_wavelet()

        self._recompute_excursion(excursion_cfg, scale_y)

    # ---------- internal ----------

    def _append_tail(
        self,
        mc: MotionCurveResult,
        shift_px: int,
        full_mask: Optional[np.ndarray],
    ) -> None:
        """curve buffer append 右尾 shift_px；mask buffer append + heavy refresh-recent。"""
        s = shift_px
        init_t = mc.init_diaphragm[-s:]
        st_t = mc.smoothed_trough[-s:]
        sc_t = mc.smoothed_crest[-s:]
        pt_t = mc.diaphragm_p_trough[-s:]
        pc_t = mc.diaphragm_p_crest[-s:]

        if self.stitched_init_diaphragm is None:
            self.stitched_init_diaphragm = init_t.copy()
            self.stitched_smoothed_trough = st_t.copy()
            self.stitched_smoothed_crest = sc_t.copy()
            self.stitched_p_trough = pt_t.copy()
            self.stitched_p_crest = pc_t.copy()
            # 首個 ingest 幀必為 heavy（caller 保證 full_mask 非 None）
            self.stitched_diaphragm_mask = full_mask[:, -s:].copy()
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
            # light：沿用 buffer 最右欄補 s 欄（暫填，下個 heavy refresh 覆蓋）
            # heavy：取 full_mask 右尾 s 欄
            if full_mask is not None:
                mask_t = full_mask[:, -s:]
            else:
                mask_t = np.repeat(self.stitched_diaphragm_mask[:, -1:], s, axis=1)
            self.stitched_diaphragm_mask = np.concatenate(
                [self.stitched_diaphragm_mask, mask_t], axis=1)

        # heavy refresh-recent：frame[i] 含最近 ~frame_width 歷史，右對齊覆蓋 buffer
        # 最右 min(frame_width, full_width) 欄 → 補回 peak 落後偵測的精度缺口
        if full_mask is not None:
            k = min(full_mask.shape[1], self.stitched_diaphragm_mask.shape[1])
            self.stitched_diaphragm_mask[:, -k:] = full_mask[:, -k:]

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
