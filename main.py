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
"""
import numpy as np

from algorithm import FrameResult
from algorithm.diaphragm_detection import detect
from algorithm.excursion import brightness_way, compute_peak_info
from algorithm.motion_curve import extract_motion_curve
from algorithm.roi_band import (
    compute_target_y_range,
    enhanced_search,
    select_target,
)
from algorithm.segmentation import PaddleSegSegmenter
from config import Phase, RunBundle
from input import apply_dicom_crop, load
from visualization.pipeline_visualizer import PipelineVisualizer


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

    # 4. Visualizer
    pv = PipelineVisualizer(bundle.viz, bundle.excursion)

    is_excursion = (phase == Phase.EXCURSION)

    # 4. 逐 frame pipeline
    gray_frames = seq.as_gray()
    color_frames = seq.as_color()       # Final overlay base canvas（保留 DCM 原色標記）
    results = []
    n = len(seq.frames)
    for i, frame in enumerate(seq.frames):
        gray = gray_frames[i]
        color = color_frames[i]

        # 4a. Paddle segmentation → uint8 mask
        mask_pil = segmenter.predict(
            image_path=seq.source_path,
            dcm_array=frame,
        )
        seg_mask = np.array(mask_pil.convert("L"), dtype=np.uint8)

        # 4b. Diaphragm detection (pass 1, segment-aided)
        detection = detect(gray, bundle.detection, use_segment=seg_mask)

        # 4c. ROI band 擴張
        y_band = compute_target_y_range(
            target_y_range=detection.best_region,
            image_height=gray.shape[0],
            reserve_ratio=bundle.roi_band.reserve_ratio,
        )

        # 4d. Enhanced search (pass 2, classical 強化路徑)
        refined = enhanced_search(
            image_gray=gray,
            y_band=y_band,
            detection_config=bundle.detection,
            roi_band_config=bundle.roi_band,
        )

        # 4e. 選定下游 excursion 用的 target / mask
        selection = select_target(
            detection_pass1=detection,
            refined=refined,
            y_band=y_band,
            image_shape=gray.shape[:2],
            use_segment_label=bundle.roi_band.use_segment_label,
        )

        import cv2
        # 4f. 抽橫膈膜時序軌跡
        motion_curve = extract_motion_curve(
            image=cv2.medianBlur(gray, 7),
            y_range=y_band,
            config=bundle.motion_curve,
        )

        # 4g. Excursion 主算法（只在 excursion phase 跑）
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

            # 4h. 物理量計算（excursion phase：scale_x 不傳 → time/velocity 為 None）
            scale_y = seq.metadata.get('physical_delta_y')
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
        results.append(result)
        pv.render_frame(
            frame_idx=i,
            image_gray=gray,
            image_color=color,
            seg_mask=seg_mask,
            frame_result=result,
        )

        if i == 0 or (i + 1) % 10 == 0 or i == n - 1:
            n_batches = len(excursion.batches) if excursion else 0
            first_cm = (
                measurements[0].excursion_cm if measurements else None
            )
            print(f"[frame {i+1}/{n}] "
                  f"best={detection.best_region}, y_band={y_band}, "
                  f"source={selection.source}, "
                  f"target={selection.target_binary is not None}, "
                  f"broken={len(motion_curve.broken_indices)}, "
                  f"batches={n_batches}, excursion_cm={first_cm}")

    n_selected = sum(1 for r in results if r.selection.target_binary is not None)
    n_excursion = sum(1 for r in results if r.excursion is not None)
    print(f"[done] {len(results)} frames, "
          f"target_binary={n_selected}, excursion_runs={n_excursion}")
    return seq, results


if __name__ == "__main__":
    image_path = (
        r"E:\PeterMC_Tsai\Diaphragm_data\Quality_Classification_base_up_down\Dicom_ex"
        r"\Excursion-QB\1017(new))\Peter\Peter_Quiet_1.dcm"
    )
    run(image_path)
