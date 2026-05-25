"""Skeleton + curve fitting，用來從多個 candidate region 中挑出最像橫膈膜「曲線」的一個。

Pipeline (per candidate):
    binary region
      → skeletonize             # 抽骨架
      → prune short branches    # 修剪短分支
      → sample (y vs x)         # 取沿 x 的 y 軌跡
      → wavelet denoising
      → poly+sin curve fit      # 分段擬合
      → morphological score     # 多特徵加權評分（peak/valley count + energy + position）

直接搬自 diaphragm_curve_fit.py：
  - 邏輯不動
  - 寫死的 prune length 100 → 改參數 prune_branch_max_length（預設仍 100，行為一致）
  - 移除未使用的 import peak_widths
  - 加 docstring / type hints
  - print 保留（migration 階段不改 logging）

外部依賴：
  - stable_peak.wavelet_denoising（暫放 repo root；之後找適當位置）
"""
from typing import List, Tuple

import cv2
import numpy as np
from scipy.ndimage import convolve
from scipy.optimize import curve_fit
from scipy.signal import find_peaks
from skimage.morphology import skeletonize

from algorithm.signal_processing import wavelet_denoising


# ---------- 評分 ----------

def morphological_comparison(y_original: np.ndarray, y_fit: np.ndarray):
    """用峰谷數、能量差、峰位差等多特徵加權算相似度（越小越相似）。"""
    # 標準化兩個訊號
    y_orig_norm = (y_original - np.mean(y_original)) / (np.std(y_original) or 1)
    y_fit_norm = (y_fit - np.mean(y_fit)) / (np.std(y_fit) or 1)

    orig_peaks, _ = find_peaks(y_orig_norm, distance=20)
    fit_peaks, _ = find_peaks(y_fit_norm, distance=20)
    orig_valleys, _ = find_peaks(-y_orig_norm, distance=20)
    fit_valleys, _ = find_peaks(-y_fit_norm, distance=20)

    features = {
        'peak_count_diff': abs(len(orig_peaks) - len(fit_peaks)),
        'valley_count_diff': abs(len(orig_valleys) - len(fit_valleys)),
        'energy_diff': np.sum((y_orig_norm - y_fit_norm) ** 2),
    }

    peak_position_similarity = 0
    if len(orig_peaks) > 0 and len(fit_peaks) > 0:
        orig_peaks_norm = orig_peaks / len(y_original)
        fit_peaks_norm = fit_peaks / len(y_fit)
        min_dists = [
            min(abs(op - fp) for fp in fit_peaks_norm) for op in orig_peaks_norm
        ]
        peak_position_similarity = np.mean(min_dists)
    features['peak_position_diff'] = peak_position_similarity

    weights = {
        'peak_count_diff': 1.0,
        'valley_count_diff': 1.0,
        'energy_diff': 1.0,
        'peak_position_diff': 1.0,
    }
    similarity_score = sum(weights[k] * features[k] for k in weights)
    return similarity_score, features


# ---------- Helper ----------

def normalize_to_01(data: np.ndarray) -> np.ndarray:
    min_val = np.min(data)
    max_val = np.max(data)
    if max_val == min_val:
        return np.zeros_like(data)
    return (data - min_val) / (max_val - min_val)


# ---------- Fit models ----------

def sine_func(x, amp, freq, phase, offset):
    return amp * np.cos(freq * x + phase) + offset


def poly_sin(x, a, b, c, A, f, phi):
    return a * x ** 2 + b * x + c + A * np.cos(f * x + phi)


# ---------- Single-section fit ----------

def curve_fit_by_part(points_data: np.ndarray, fit_func):
    """對單一段點集做 wavelet 降噪後的曲線擬合。

    points_data: shape (N, 2)，points[:, 0] 是 y、points[:, 1] 是 x
    """
    y_values = wavelet_denoising(1 - normalize_to_01(points_data[:, 0]))
    x_values = np.arange(len(points_data[:, 1]))

    init_guess = [0, 0, np.mean(y_values), np.std(y_values),
                  2 * np.pi / len(x_values), 0]

    try:
        params, _ = curve_fit(fit_func, x_values, y_values, p0=init_guess, maxfev=10000000)
        y_fit = fit_func(x_values, *params)
        mse = np.mean((y_values - y_fit) ** 2)
    except Exception as e:
        mse = 1000
        y_fit = y_values - 10000
        print(e)

    return mse, x_values, y_values, y_fit


# ---------- 主入口 ----------

def diaphragm_curve_fit(
    potential_diaphragm_regions: List[Tuple[int, int, int]],
    labels: np.ndarray,
    b_image: np.ndarray,
    sections: int = 1,
    prune_branch_max_length: int = 100,
):
    """對每個 candidate 做骨架抽取 + 曲線擬合 + 評分，回傳最佳者。

    Args:
        potential_diaphragm_regions: [(label_idx, top, bottom), ...]
        labels: connected components 的 label map
        b_image: binary mask（shape 提供用）
        sections: 把骨架點切成幾段分別擬合
        prune_branch_max_length: 修剪短分支的長度上限

    Returns:
        (mse_idx, regions)：list 各一個元素，分別是 best label index 與其 (top, bottom)
    """
    mse_min = 10000000  # 留著（commented-out 分支用）
    score_min = 10000000
    mse_idx: List[int] = []
    regions: List[Tuple[int, int]] = []
    best_region = None
    best_idx = -2

    for idx, top, bottom in potential_diaphragm_regions:
        skeleton_map = np.zeros(b_image.shape).astype("uint8")
        step1_filtered_binary = np.zeros(b_image.shape).astype("uint8")
        step1_filtered_binary[labels == idx] = 255

        # 填補孔洞
        contours, hierarchy = cv2.findContours(
            step1_filtered_binary, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        for i, cnt in enumerate(contours):
            next_cnt, prev_cnt, first_child, parent = hierarchy[0][i]
            if parent != -1:
                cv2.drawContours(step1_filtered_binary, contours, i, 255, -1)

        # 抽骨架
        img_skeleton = skeletonize(step1_filtered_binary)

        # 偵測端點與分支點
        kernel = np.array([[1, 1, 1],
                           [1, 0, 1],
                           [1, 1, 1]])
        neighbors = convolve(img_skeleton.astype(int), kernel, mode='constant', cval=0)
        endpoints = (img_skeleton > 0) & (neighbors == 1)

        # 修剪短分支
        pruned_skeleton = img_skeleton.copy()
        for y, x in np.argwhere(endpoints):
            if pruned_skeleton[y, x]:
                current = (y, x)
                length = 0
                while length < prune_branch_max_length:
                    nb = [(i, j)
                          for i in range(current[0] - 1, current[0] + 2)
                          for j in range(current[1] - 1, current[1] + 2)
                          if (i, j) != current
                          and 0 <= i < img_skeleton.shape[0]
                          and 0 <= j < img_skeleton.shape[1]]
                    next_points = [p for p in nb if pruned_skeleton[p]]
                    if len(next_points) != 1:
                        break
                    pruned_skeleton[current] = 0
                    current = next_points[0]
                    length += 1

        skeleton_map[pruned_skeleton] = 255

        # 取點並沿 x 排序
        points = np.column_stack(np.where(skeleton_map > 0))
        points = points[points[:, 1].argsort()]

        y_values_plt = wavelet_denoising(1 - normalize_to_01(points[:, 0]))
        x_values_plt = np.arange(len(points[:, 1]))

        # 分段擬合
        y_fit_ttl = None
        total_mse = 0
        split_data = np.array_split(points, indices_or_sections=sections)
        for point in split_data:
            mse, x_values, y_values, y_fit = curve_fit_by_part(
                points_data=point, fit_func=poly_sin)
            total_mse += mse
            y_fit_ttl = y_fit if y_fit_ttl is None else np.hstack((y_fit_ttl, y_fit))

        # 評分
        score, features = morphological_comparison(y_values_plt, y_fit_ttl)
        if score < score_min:
            score_min = score
            best_idx = idx
            best_region = (top, bottom)

    mse_idx.append(best_idx)
    regions.append(best_region)
    print("[Diaphragm Curve Fit] mse_idx: ", mse_idx)
    return mse_idx, regions
