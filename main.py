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
import cv2
import numpy as np

from algorithm import FrameResult
from algorithm.diaphragm_detection import detect
from algorithm.excursion import brightness_way, compute_peak_info
from algorithm.motion_curve import extract_motion_curve
from algorithm.multiframe import (
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
) -> FrameResult:
    """單 frame pipeline；LEGACY 與 GLOBAL_WINDOW 兩 mode 共用。"""
    frame = seq.frames[i]

    mask_pil = segmenter.predict(
        image_path=seq.source_path,
        dcm_array=frame,
    )
    seg_mask = np.array(mask_pil.convert("L"), dtype=np.uint8)

    detection = detect(gray, bundle.detection, use_segment=seg_mask)

    y_band = compute_target_y_range(
        target_y_range=detection.best_region,
        image_height=gray.shape[0],
        reserve_ratio=bundle.roi_band.reserve_ratio,
    )

    refined = enhanced_search(
        image_gray=gray,
        y_band=y_band,
        detection_config=bundle.detection,
        roi_band_config=bundle.roi_band,
    )

    selection = select_target(
        detection_pass1=detection,
        refined=refined,
        y_band=y_band,
        image_shape=gray.shape[:2],
        use_segment_label=bundle.roi_band.use_segment_label,
    )

    motion_curve = extract_motion_curve(
        image=cv2.medianBlur(gray, 7),
        y_range=y_band,
        config=bundle.motion_curve,
    )

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
    return result


def run(image_path: str, phase: Phase = Phase.EXCURSION):
    # 1. Load + crop
    seq = load(image_path)
    print(f"[input] source_type={seq.source_type}, "
          f"frames.shape={seq.frames.shape}, fps={seq.fps}")

    seq = apply_dicom_crop(seq)
    print(f"[preprocess] cropped frames.shape={seq.frames.shape}")

    if seq.source_type == 'png_dir':
        raise NotImplementedError(
            "PNG dir → segmenter 整合尚未完成。需後續 patch 把 inner predict "
            "改為優先使用 pixel_array、不再 by-extension dispatch。"
        )

    # 2. 配置聚合（一行 init 全部 cfg；for_phase 只代 detection，其他用 default）
    bundle = RunBundle.for_phase(phase)

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


if __name__ == "__main__":
    image_path = (
        r"E:\PeterMC_Tsai\Diaphragm_data\Quality_Classification_base_up_down\Dicom_ex"
        r"\Excursion-QB\26_0511\1776049685152\20260511\Peter_Quiet_1.dcm"
    )
    run(image_path)
