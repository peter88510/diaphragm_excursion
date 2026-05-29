"""Diaphragm excursion — main entry point.

Pipeline (per frame):
    load(path)             → FrameSequence
    apply_dicom_crop()     → cropped FrameSequence
    PaddleSegSegmenter     → seg mask (PIL)
    detect()               → DetectionResult (pass 1, segment-aided)
    compute_target_y_range → y_band (擴張)
    enhanced_search        → RoiSearchResult (pass 2, classical 強化路徑)
    select_target          → TargetSelection (依 RoiBandConfig.use_segment_label 選 mask 來源)
    extract_motion_curve   → MotionCurveResult (橫膈膜軌跡)
    brightness_way         → ExcursionResult (excursion phase: 找 peak/trough)

Multi-frame dispatch（依 MultiframeConfig.mode）：
    LEGACY        : per-frame loop（傳統行為）
    GLOBAL_WINDOW : 抽 2 keyframe → 各跑 single-frame → run_global_window 拼接 → global final viz
"""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from algorithm import FrameResult
from algorithm.diaphragm_detection import detect
from algorithm.excursion import brightness_way, compute_peak_info
from algorithm.motion_curve import MotionCurveResult, extract_motion_curve
from algorithm.multiframe import (
    RealtimeState,
    estimate_shift,
    get_keyframe_indices,
    get_legacy_frame_indices,
    run_global_window,
)
from algorithm.roi_band import (
    compute_target_y_range,
    enhanced_search,
    select_target,
)
from algorithm.segmentation import PaddleSegSegmenter
from config import Phase, RunBundle
from config.multiframe_config import MultiframeMode
from input import apply_dicom_crop, load
from visualization.global_window import render_global_final
from visualization.pipeline_visualizer import PipelineVisualizer
from visualization.realtime import render_realtime_canvas, render_realtime_global


@dataclass
class RealtimeTiming:
    """REALTIME per-stage 計時累計（profiling；不參與演算法計算）。"""
    totals: dict = field(default_factory=lambda: defaultdict(float))
    counts: dict = field(default_factory=lambda: defaultdict(int))

    def record(self, stage: str, dt: float) -> None:
        self.totals[stage] += dt
        self.counts[stage] += 1

    def report(self, loop_total: float) -> None:
        """印 Layer A（每幀時間去向，% loop）+ Layer B（heavy 內部，% heavy）。"""
        layer_a = ["shift", "heavy", "light", "ingest", "viz"]
        layer_b = ["seg_predict", "detect_roi", "motion_curve",
                   "excursion_sf", "pv_render"]
        layer_c = ["detect_p1", "enhance", "detect_p2", "select"]
        heavy_total = self.totals.get("heavy", 0.0)
        detect_roi_total = self.totals.get("detect_roi", 0.0)

        def _line(stage: str, denom: float) -> Optional[str]:
            n = self.counts.get(stage, 0)
            if n == 0:
                return None
            tot = self.totals.get(stage, 0.0)
            avg_ms = tot / n * 1000
            pct = tot / denom * 100 if denom else 0.0
            return (f"    {stage:<13}{tot:8.2f}s {n:5d}x "
                    f"{avg_ms:8.1f} ms {pct:5.1f}%")

        print(f"[realtime-timing] loop_total={loop_total:.2f}s")
        print("  Layer A: per-frame time (% loop)")
        for s in layer_a:
            line = _line(s, loop_total)
            if line:
                print(line)
        print("  Layer B: heavy internal breakdown (% heavy)")
        for s in layer_b:
            line = _line(s, heavy_total)
            if line:
                print(line)
        print("  Layer C: detect_roi breakdown (% detect_roi)")
        for s in layer_c:
            line = _line(s, detect_roi_total)
            if line:
                print(line)


def _run_single_frame(
    seq,
    i: int,
    gray: np.ndarray,
    color: np.ndarray,
    segmenter: PaddleSegSegmenter,
    pv: PipelineVisualizer,
    bundle: RunBundle,
    is_excursion: bool,
    scale_y,
    timing: Optional[RealtimeTiming] = None,
) -> FrameResult:
    """單 frame pipeline；LEGACY 與 GLOBAL_WINDOW 兩 mode 共用。

    timing 非 None（REALTIME heavy 幀）時記錄 Layer B 各子步驟耗時；None 時零影響。
    """
    frame = seq.frames[i]

    t0 = time.perf_counter()
    mask_pil = segmenter.predict(
        image_path=seq.source_path,
        dcm_array=frame,
    )
    seg_mask = np.array(mask_pil.convert("L"), dtype=np.uint8)
    if timing is not None:
        timing.record("seg_predict", time.perf_counter() - t0)
        t0 = time.perf_counter()

    detection = detect(gray, bundle.detection, use_segment=seg_mask)

    y_band = compute_target_y_range(
        target_y_range=detection.best_region,
        image_height=gray.shape[0],
        reserve_ratio=bundle.roi_band.reserve_ratio,
    )
    if timing is not None:
        timing.record("detect_p1", time.perf_counter() - t0)

    refined = enhanced_search(           # 內部記 enhance / detect_p2（Layer C）
        image_gray=gray,
        y_band=y_band,
        detection_config=bundle.detection,
        roi_band_config=bundle.roi_band,
        timing=timing,
    )

    t_sel = time.perf_counter()
    selection = select_target(
        detection_pass1=detection,
        refined=refined,
        y_band=y_band,
        image_shape=gray.shape[:2],
        use_segment_label=bundle.roi_band.use_segment_label,
    )
    if timing is not None:
        now = time.perf_counter()
        timing.record("select", now - t_sel)
        timing.record("detect_roi", now - t0)   # rollup（Layer B）
        t0 = now

    motion_curve = extract_motion_curve(
        image=cv2.medianBlur(gray, 7),
        y_range=y_band,
        config=bundle.motion_curve,
    )
    if timing is not None:
        timing.record("motion_curve", time.perf_counter() - t0)
        t0 = time.perf_counter()

    excursion = None
    measurements = []
    if is_excursion:
        excursion = brightness_way(
            diaphragm_mask=selection.diaphragm_mask,
            diaphragm_p_4crest=motion_curve.diaphragm_p_crest,
            diaphragm_p_4trough=motion_curve.diaphragm_p_trough,
            diaphragm_ori_y_value=motion_curve.init_diaphragm,
            config=bundle.excursion,
        )
        measurements = [
            compute_peak_info(
                crest=batch.crest_position,
                trough=batch.trough_position,
                scale_y=scale_y,
            )
            for batch in excursion.batches
        ]
    if timing is not None:
        timing.record("excursion_sf", time.perf_counter() - t0)
        t0 = time.perf_counter()

    result = FrameResult(
        detection=detection,
        y_band=y_band,
        refined=refined,
        selection=selection,
        motion_curve=motion_curve,
        excursion=excursion,
        measurements=measurements,
    )
    pv.render_frame(
        frame_idx=i,
        image_gray=gray,
        image_color=color,
        seg_mask=seg_mask,
        frame_result=result,
    )
    if timing is not None:
        timing.record("pv_render", time.perf_counter() - t0)
    return result


def _run_light_frame(gray: np.ndarray, y_band, bundle: RunBundle) -> MotionCurveResult:
    """REALTIME light tier：沿用 cached y_band 只跑 motion_curve（不跑 paddle）。"""
    return extract_motion_curve(
        image=cv2.medianBlur(gray, 7),
        y_range=y_band,
        config=bundle.motion_curve,
    )


def _max_peak_x(excursion) -> int:
    """rolling excursion 中最右側被選中的 crest/trough x（無則 -1）；供峰觸發判斷。"""
    if excursion is None:
        return -1
    xs = []
    for b in excursion.batches:
        xs.extend(b.selected_crest_x)
        xs.extend(b.selected_trough_x)
    return max(xs) if xs else -1


def run(
    image_path: str,
    phase: Phase = Phase.EXCURSION,
    bundle: Optional[RunBundle] = None,
):
    # 1. 配置聚合（外部可注入 bundle；None 時用 for_phase canonical default）
    if bundle is None:
        bundle = RunBundle.for_phase(phase)

    # 2. Load + crop
    seq = load(image_path)
    print(f"[input] source_type={seq.source_type}, "
          f"frames.shape={seq.frames.shape}, fps={seq.fps}")

    seq = apply_dicom_crop(seq, bundle.dicom_crop)
    print(f"[preprocess] cropped frames.shape={seq.frames.shape}")

    if seq.source_type == 'png_dir':
        raise NotImplementedError(
            "PNG dir → segmenter 整合尚未完成。需後續 patch 把 inner predict "
            "改為優先使用 pixel_array、不再 by-extension dispatch。"
        )

    # 3. Segmenter（lazy load；model 只 load 一次）
    segmenter = PaddleSegSegmenter(bundle.segmenter)
    segmenter.load()

    # 4. Visualizer（debug + single-frame final track）
    pv = PipelineVisualizer(bundle.viz, bundle.excursion)

    is_excursion = (phase == Phase.EXCURSION)
    scale_y = seq.metadata.get('physical_delta_y')

    gray_frames = seq.as_gray()
    color_frames = seq.as_color()       # Final overlay base canvas（保留 DCM 原色標記）

    # 5. Mode dispatch
    if bundle.multiframe.mode == MultiframeMode.LEGACY:
        results = _run_legacy(
            seq, gray_frames, color_frames, segmenter, pv, bundle,
            is_excursion, scale_y,
        )
    elif bundle.multiframe.mode == MultiframeMode.GLOBAL_WINDOW:
        results = _run_global_window(
            seq, gray_frames, color_frames, segmenter, pv, bundle,
            is_excursion, scale_y,
        )
    elif bundle.multiframe.mode == MultiframeMode.REALTIME:
        results = _run_realtime(
            seq, gray_frames, color_frames, segmenter, pv, bundle,
            is_excursion, scale_y,
        )
    else:
        raise NotImplementedError(
            f"Mode {bundle.multiframe.mode} 尚未整合進 main.py"
        )

    n_selected = sum(1 for r in results if r.selection.target_binary is not None)
    n_excursion = sum(1 for r in results if r.excursion is not None)
    print(f"[done] {len(results)} frames, "
          f"target_binary={n_selected}, excursion_runs={n_excursion}")
    return seq, results


def _run_legacy(
    seq, gray_frames, color_frames, segmenter, pv, bundle, is_excursion, scale_y,
):
    frame_indices = get_legacy_frame_indices(bundle.multiframe, seq)
    verbose_log = bundle.multiframe.legacy_frame_indices is not None
    n = len(seq.frames)
    results = []
    for i in frame_indices:
        result = _run_single_frame(
            seq, i, gray_frames[i], color_frames[i],
            segmenter, pv, bundle, is_excursion, scale_y,
        )
        results.append(result)

        if verbose_log or i == 0 or (i + 1) % 10 == 0 or i == n - 1:
            n_batches = len(result.excursion.batches) if result.excursion else 0
            first_cm = (
                result.measurements[0].excursion_cm if result.measurements else None
            )
            print(f"[frame {i+1}/{n}] "
                  f"best={result.detection.best_region}, y_band={result.y_band}, "
                  f"source={result.selection.source}, "
                  f"target={result.selection.target_binary is not None}, "
                  f"broken={len(result.motion_curve.broken_indices)}, "
                  f"batches={n_batches}, excursion_cm={first_cm}")
    return results


def _run_global_window(
    seq, gray_frames, color_frames, segmenter, pv, bundle, is_excursion, scale_y,
):
    kf_indices = get_keyframe_indices(bundle.multiframe, seq)
    if len(kf_indices) != 2:
        raise ValueError(
            f"GLOBAL_WINDOW 需嚴格 2 個 keyframe；got {kf_indices}"
        )

    results = [
        _run_single_frame(
            seq, i, gray_frames[i], color_frames[i],
            segmenter, pv, bundle, is_excursion, scale_y,
        )
        for i in kf_indices
    ]
    for i, r in zip(kf_indices, results):
        n_batches = len(r.excursion.batches) if r.excursion else 0
        first_cm = r.measurements[0].excursion_cm if r.measurements else None
        print(f"[keyframe {i}] "
              f"best={r.detection.best_region}, y_band={r.y_band}, "
              f"source={r.selection.source}, batches={n_batches}, "
              f"excursion_cm={first_cm}")

    if not is_excursion:
        return results

    global_result = run_global_window(
        keyframe_motion_curves=[r.motion_curve for r in results],
        keyframe_selections=[r.selection for r in results],
        multiframe_cfg=bundle.multiframe,
        excursion_cfg=bundle.excursion,
        scale_y=scale_y,
    )
    n_global = len(global_result.measurements)
    first_global_cm = (
        global_result.measurements[0].excursion_cm
        if global_result.measurements else None
    )
    print(f"[global] full_width={global_result.full_width}, "
          f"boundary_x={global_result.stitch_boundary_x}, "
          f"batches={n_global}, excursion_cm={first_global_cm}")

    render_global_final(
        global_result=global_result,
        image_color_first=color_frames[kf_indices[0]],
        image_color_second=color_frames[kf_indices[1]],
        cfg=bundle.viz,
        excursion_cfg=bundle.excursion,
    )
    return results


def _run_realtime(
    seq, gray_frames, color_frames, segmenter, pv, bundle, is_excursion, scale_y,
):
    """REALTIME mode：逐 frame 累積（frame[0] 跳過）+ 分層 cadence + 雙 track viz。

    分層 cadence（Patch 19）避免每幀跑 paddle：
      - estimate_shift 前移：無效幀（delay / 低信心 / 後退）直接跳過，省 paddle
      - light tier（多數幀）：沿用 cached y_band 只跑 motion_curve
      - heavy tier（paddle 整張 frame）：bootstrap / 峰觸發 / 距上次 heavy ≥ K_max
    mask 採 refresh-recent（見 RealtimeState._append_tail）。ingest_frame 為
    streaming-ready 接口。
    """
    mf = bundle.multiframe
    n = len(seq.frames)
    stop = min(n, mf.realtime_max_frames or n)
    warmup = mf.realtime_warmup_frames
    k_max = mf.realtime_seg_refresh_max_n

    state = RealtimeState(
        algorithm_min_width=mf.realtime_algorithm_min_width,
        wavelet_refresh_every_n=mf.realtime_wavelet_refresh_every_n,
        wavelet_level_trough=bundle.motion_curve.wavelet_level_trough,
        wavelet_level_crest=bundle.motion_curve.wavelet_level_crest,
    )
    timing = RealtimeTiming()

    print("[realtime] frame 0 skipped (probe init)")
    results = []
    prev_gray = gray_frames[0]          # frame 0 作 shift 參考，不 ingest
    cached_y_band = None                # heavy 幀刷新；light 幀沿用
    frames_since_heavy = 0
    last_peak_x = -1
    pending_peak_heavy = False
    n_skip = 0

    loop_start = time.perf_counter()
    for i in range(1, stop):
        gray = gray_frames[i]

        # 1. estimate_shift 前移（cheap）→ 無效幀跳過，省 paddle
        t = time.perf_counter()
        shift = estimate_shift(
            prev_gray, gray, mf.realtime_shift_strategy,
            stride_pixel=mf.stride_pixel,
            min_confidence=mf.realtime_shift_min_confidence,
        )
        timing.record("shift", time.perf_counter() - t)
        prev_gray = gray

        if not (is_excursion and shift.found and shift.shift_px > 0):
            n_skip += 1
            print(f"[realtime {i}/{stop - 1}] "
                  f"shift={shift.shift_px} (raw={shift.raw_shift:.2f}, "
                  f"conf={shift.confidence:.3f}, found={shift.found}), "
                  f"skip (no paddle)")
            continue

        is_warmup = i <= warmup

        # 2. tier 決策：bootstrap / K_max fallback / 峰觸發（warmup 期不峰精修）
        need_heavy = (
            cached_y_band is None
            or frames_since_heavy >= k_max
            or (pending_peak_heavy and not is_warmup)
        )
        pending_peak_heavy = False

        # 3. 跑該 tier 取 motion_curve（heavy 才有 full_mask + 刷新 y_band）
        if need_heavy:
            t = time.perf_counter()
            result = _run_single_frame(
                seq, i, gray, color_frames[i],
                segmenter, pv, bundle, is_excursion, scale_y, timing=timing,
            )
            timing.record("heavy", time.perf_counter() - t)
            results.append(result)
            cached_y_band = result.y_band
            motion_curve = result.motion_curve
            full_mask = result.selection.diaphragm_mask
            frames_since_heavy = 0
        else:
            t = time.perf_counter()
            motion_curve = _run_light_frame(gray, cached_y_band, bundle)
            timing.record("light", time.perf_counter() - t)
            full_mask = None
            frames_since_heavy += 1

        # 4. ingest（refresh-recent mask）+ rolling excursion
        t = time.perf_counter()
        state.ingest_frame(
            motion_curve, i, shift.shift_px,
            bundle.excursion, scale_y, full_mask=full_mask,
        )
        timing.record("ingest", time.perf_counter() - t)

        # 5. piggyback：偵測到更右側新峰 → 下一幀 heavy（補峰精度）
        max_peak_x = _max_peak_x(state.excursion)
        if max_peak_x > last_peak_x:
            pending_peak_heavy = True
            last_peak_x = max_peak_x

        # 6. 雙 track viz（global 完整 / canvas 右錨定視窗）
        t = time.perf_counter()
        render_realtime_global(
            frame_idx=i, state=state, color_frames=color_frames,
            is_warmup=is_warmup, warmup_total=warmup,
            cfg=bundle.viz, excursion_cfg=bundle.excursion,
        )
        render_realtime_canvas(
            frame_idx=i, image_color=color_frames[i], state=state,
            is_warmup=is_warmup, warmup_total=warmup,
            cfg=bundle.viz, excursion_cfg=bundle.excursion,
        )
        timing.record("viz", time.perf_counter() - t)

        tier = "heavy" if need_heavy else "light"
        status = "warmup" if is_warmup else (
            "computing" if state.excursion is None else "ready")
        gcm = state.measurements[0].excursion_cm if state.measurements else None
        print(f"[realtime {i}/{stop - 1}] "
              f"shift={shift.shift_px}, {tier}, "
              f"width={state.full_width}, {status}, global_cm={gcm}")

    loop_total = time.perf_counter() - loop_start
    print(f"[realtime] frames: heavy={timing.counts['heavy']} "
          f"light={timing.counts['light']} skip={n_skip}")
    timing.report(loop_total)
    return results


if __name__ == "__main__":
    try:
        import run_config as rc
    except ImportError:
        raise SystemExit(
            "缺 run_config.py — 請複製 run_config.example.py 為 run_config.py "
            "並填入 IMAGE_PATH"
        )
    run(rc.IMAGE_PATH, bundle=rc.build_bundle())
