"""Excursion 主算法：brightness_way（依亮度曲線找波峰波谷 + segment 修邊界）。

對應原 excursion_rule.py 的 brightness_way。Pipeline:
    diaphragm_p_4crest / diaphragm_p_4trough     (motion_curve 輸出)
        ↓ find_peaks                              （只給 debug viz 用）
        ↓ find_midline → crossings, rise_or_decline
        ↓ excursion_rule 依 crossings 數量規則選 peak / trough
        ↓ find_boundary（舊 util FindBoundary 重構）  用 segment mask 修正位置
    回傳 ExcursionResult (含 batches)

差異 vs 原版：
  - 移除 image_store 參數；改吃 diaphragm_mask（直接傳）
  - 移除 x_dim 參數；改從 diaphragm_p_4trough.shape[0] 推導
  - 移除 args 參數；debug 改為 debug: bool flag
  - 移除 matplotlib.use('TkAgg') 全域副作用（不在 module 內動 backend）
  - 7-tuple 回傳改 ExcursionResult dataclass（每 batch 為 ExcursionBatch）
  - 寫死的 distance=50/1500、prominence=10、min_distance=100 進 ExcursionConfig
  - 保留 print（migration 階段不動 logging）
  - 9D：debug 渲染已搬到 visualization.layers.excursion，本檔不再依賴 matplotlib
"""
from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

from algorithm.excursion.boundary import find_boundary
from algorithm.excursion.midline import find_midline
from algorithm.excursion.rules import excursion_rule
from config import ExcursionConfig


@dataclass
class ExcursionBatch:
    """一個 crossing batch 算出的 peak/trough 配對。"""
    crest_position: Tuple[int, int]                # (x, y) 已被 find_boundary 修正
    trough_position: Tuple[int, int]
    selected_crest_x: List[int]                    # excursion_rule 選出的 x indices
    selected_trough_x: List[int]
    crest_bar_max_peak: List[int]                  # 對應 diaphragm_ori_y_value 的 y 值
    trough_bar_max_peak: List[int]


@dataclass
class ExcursionResult:
    batches: List[ExcursionBatch]                  # 一或多組（依 crossings 數）
    crossings: np.ndarray                          # 全部 crossings（debug）
    rise_or_decline: np.ndarray                    # 全部方向標籤（debug）


def brightness_way(
    diaphragm_mask: np.ndarray,
    diaphragm_p_4crest: np.ndarray,
    diaphragm_p_4trough: np.ndarray,
    diaphragm_ori_y_value: np.ndarray,
    config: ExcursionConfig,
) -> ExcursionResult:
    """Excursion 主算法：找出 peak/trough 配對並用 mask 修正位置。

    Args:
        diaphragm_mask: 從 TargetSelection.diaphragm_mask 取得（segment 修邊界用）
        diaphragm_p_4crest: motion_curve 的波峰用平滑曲線
        diaphragm_p_4trough: motion_curve 的波谷用平滑曲線
        diaphragm_ori_y_value: motion_curve 的原始軌跡（給 selected_x 取對應 y）
        config: ExcursionConfig
    """
    # 中線與穿越線
    x_dim = len(diaphragm_p_4trough)
    midline_min_distance_px = round(config.midline_min_distance_ratio * x_dim)
    crossings, rise_or_decline = find_midline(
        diaphragm_y_value=diaphragm_p_4trough,
        min_distance=midline_min_distance_px,
    )

    # 依 crossings 數量分批
    if len(crossings) > 2:
        crossings_list = [crossings[i:i + 2] for i in range(0, len(crossings) - 1, 2)]
        rise_or_decline_list = [
            rise_or_decline[i:i + 2] for i in range(0, len(rise_or_decline) - 1, 2)
        ]
    else:
        crossings_list = [crossings]
        rise_or_decline_list = [rise_or_decline]

    # 每批跑 excursion_rule → 收 selected peaks/troughs
    rule_results: List[Tuple[List[int], List[int]]] = []
    for c_batch, r_batch in zip(crossings_list, rise_or_decline_list):
        selected_troughs, selected_crest = excursion_rule(
            c_batch, r_batch,
            diaphragm_y_value=diaphragm_p_4trough,
            start_range=config.excursion_rule_start_range,
            end_range=config.excursion_rule_end_range,
        )
        print(selected_troughs, selected_crest)
        rule_results.append((selected_troughs, selected_crest))

    # 每批做 boundary refine
    batches: List[ExcursionBatch] = []
    for selected_troughs, selected_crest in rule_results:
        crest_bar_max_peak = list(diaphragm_ori_y_value[selected_crest])
        trough_bar_max_peak = list(diaphragm_ori_y_value[selected_troughs])

        crest_position, trough_position = find_boundary(
            diaphragm_mask=diaphragm_mask,
            selected_x_crest=selected_crest,
            selected_y_crest=crest_bar_max_peak,
            selected_x_trough=selected_troughs,
            selected_y_trough=trough_bar_max_peak,
        )

        batches.append(ExcursionBatch(
            crest_position=crest_position,
            trough_position=trough_position,
            selected_crest_x=selected_crest,
            selected_trough_x=selected_troughs,
            crest_bar_max_peak=crest_bar_max_peak,
            trough_bar_max_peak=trough_bar_max_peak,
        ))

    return ExcursionResult(
        batches=batches,
        crossings=crossings,
        rise_or_decline=rise_or_decline,
    )
