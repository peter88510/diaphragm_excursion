"""Signal processing utilities（從原 repo-root stable_peak.py 搬入）。

9E 搬遷時同步移除已死的 edge_motion_curve / mask_edge_motion_curve
（取代品為 algorithm/motion_curve/extract.py 的 extract_motion_curve）。

保留：
  - wavelet_denoising：被 curve_fit 與 motion_curve 使用
  - turn_to_level / select_stable_section / align_peak / is_significant_peak_valley：
    未來 stable section / sniff 路徑可能會用到
  - extend_edge / search_edge_iterative / Connect_breakpoints / average_width_fun /
    get_skeleton_map / get_skeleton_point / find_boundary_y：
    skeleton / boundary 操作 helper，stable section 路徑可能會用到
"""
import numpy as np
import pywt
from scipy.signal import find_peaks
from collections import defaultdict
import cv2
from skimage.morphology import skeletonize
from bresenham import bresenham


def wavelet_denoising(signal, wavelet='db4', level=5):
    # 小波分解
    coeffs = pywt.wavedec(signal, wavelet, level=level)
    # 只保留低頻分量（近似係數）
    for i in range(1, len(coeffs)):
        coeffs[i] = np.zeros_like(coeffs[i])
    # 重建信號
    trend_signal = pywt.waverec(coeffs, wavelet)
    return trend_signal[:len(signal)]  # 確保長度一致


def turn_to_level(amplitudes):
    # 提取對應的振幅
    amplitudes_array = np.array(amplitudes)
    amplitudes_level = np.clip(amplitudes_array // 10 + 1, 1, 10)
    return amplitudes_level


def select_stable_section(paired_peaks, window_size=3, filter_peak=False):
    """
    找出最小標準差的一組連續波峰波谷區段。

    Args:
        window_size: 計算標準差的最小窗口大小（至少包含 N 組波峰-波谷）
        paired_peaks: 成對的波峰波谷
        :param window_size:
        :param filter_peak:

    Returns:
        start_idx: 最小標準差區段的起始索引
        end_idx: 最小標準差區段的結束索引

    """
    if filter_peak:
        paired_peaks = paired_peaks[1:-1]
        print("[Stable Peak] 第一組與最後一組波(波峰, 波谷, 波峰) 不列入計算 ")

    amplitudes = [round(abs(th[1] - ch2[1])) for ch, th, ch2 in paired_peaks]
    time = [(abs(th[0] - ch[0]), abs(ch2[0] - th[0])) for ch, th, ch2 in paired_peaks]
    if len(amplitudes) == 0:
        return paired_peaks, None, None, None, None
    # if len(amplitudes) < window_size:
    #     print(f"波峰波谷組合小於 Window Size:{window_size}")
    #     select_amp_idx = 0
    #     return 0, len(amplitudes) - 1, amplitudes, select_amp_idx  # 無法形成足夠大的區段

    while len(amplitudes) < window_size:
        if window_size == 1:
            select_amp_idx = 0
            return paired_peaks, 0, len(amplitudes) - 1, amplitudes, select_amp_idx  # 無法形成足夠大的區段
        print(f"[Stable Peak] 波峰波谷組合小於 Window Size:{window_size}")
        window_size = window_size - 1
        print(f"[Stable Peak] 調整 Window Size -> {window_size}")

    # 滑動窗口計算標準差
    min_std = float('inf')
    best_start, best_end = 0, window_size
    best_amp_section = None
    for i in range(len(amplitudes) - window_size + 1):
        window_amp = amplitudes[i:i + window_size]
        std = np.std(window_amp)
        print("[Stable Peak] window({i}): {std} {window_amp}".format(i=i, std=std, window_amp=window_amp))
        if std < min_std:
            min_std = std
            best_start, best_end = i, i + window_size
            best_amp_section = window_amp

    # best_amp_section_lv = turn_to_level(best_amp_section)
    # best_amp_section_mode = max(set(best_amp_section_lv), key=list(best_amp_section_lv).count)
    # mode_idx = [i for i, amp in enumerate(best_amp_section_lv) if amp == best_amp_section_mode]
    # select_amp_idx = best_start + mode_idx[0]

    # 2025/03/24 增加周長穩篩選(吸氣 吐氣時間差不多的波)
    best_amp_time = time[best_start:best_end]
    min_T = float('inf')
    T_idx = None
    for i, (ex, ins) in enumerate(best_amp_time):
        d = abs(ins - ex)
        if d < min_T:
            min_T = d
            T_idx = i
    select_amp_idx = best_start + T_idx

    print(f"[Stable Peak] best section window({best_start}): {best_amp_section} ({best_start} ~ {best_end - 1}), select_amp_idx: {select_amp_idx}")
    return paired_peaks, best_start, best_end, best_amp_section, select_amp_idx


def align_peak(crests, troughs, diaphragm_info_crests, diaphragm_info_troughs, correction_x=0, pattern="CTC"):
    """
        對齊波峰與波谷，回傳三點組成的配對
        pattern:
            - "CTC" : Crest - Trough - Crest
            - "TCT" : Trough - Crest - Trough
        """
    paired_peaks = []
    # crest trough crest
    if pattern == "CTC":
        main_points, secondary_points = crests, troughs
        main_info, secondary_info = diaphragm_info_crests, diaphragm_info_troughs
        miss_main_msg, miss_sec_msg = "[Align Peaks] 有波峰沒有偵測到", "[Align Peaks] 有波谷沒有偵測到"

    elif pattern == "TCT":
        main_points, secondary_points = troughs, crests
        main_info, secondary_info = diaphragm_info_troughs, diaphragm_info_crests
        miss_main_msg, miss_sec_msg = "[Align Peaks] 有波谷沒有偵測到", "[Align Peaks] 有波峰沒有偵測到"
    else:
        raise ValueError(f"未知的 pattern: {pattern}, 請使用 'CTC' 或 'TCT'")

    for i in range(len(main_points) - 1):
        x_1 = main_points[i]
        y_1 = int(main_info[x_1])  # 用lv3平滑的波峰資訊

        x_2 = main_points[i + 1]
        y_2 = int(main_info[x_2])  # 用lv3平滑的波峰資訊

        candidates = secondary_points[(secondary_points > x_1) & (secondary_points < x_2)]

        if len(candidates) == 1:
            xm = candidates[0]
            ym = int(secondary_info[xm])

            paired_peaks.append([
                (x_1 + correction_x, y_1),
                (xm + correction_x, ym),
                (x_2 + correction_x, y_2)
            ])

        elif len(candidates) > 1:  # 表示 有波峰沒有偵測到
            print(miss_main_msg)

        elif len(candidates) == 0:  # 表示有波谷沒有偵測到
            print(miss_sec_msg)

    return paired_peaks


def extend_edge(side, x_pos, upper_y, lower_y, binary_mask, step):
    # 補齊細線化左右兩端的缺
    edge_upper = search_edge_iterative(init_x=x_pos, init_y=upper_y, binary_mask=binary_mask, step=step)
    edge_lower = search_edge_iterative(init_x=x_pos, init_y=lower_y, binary_mask=binary_mask, step=step)
    edge_upper.sort(key=lambda p: p[0])
    edge_lower.sort(key=lambda p: p[0])
    if len(edge_upper) != len(edge_lower):
        raise ValueError(f"({side}) 上下邊界長度不一致: {len(edge_upper)} vs {len(edge_lower)}")

    return edge_upper, edge_lower


def search_edge_iterative(init_x, init_y, binary_mask, step):
    """
        迭代版本的邊緣搜索（推薦使用，避免遞歸深度問題）
        step = -1 往左找
        step =  1 往右找
    """
    h, w = binary_mask.shape
    edge_points = []  # [(init_x, init_y)] 出始點不要加
    current_x, current_y = init_x, init_y

    while 0 < current_x < w - 1:
        next_x = current_x + step
        found = False

        # 定義三個候選點
        for dy in [-2, -1, 0, 1, 2]:
            y = current_y + dy  # 相對起始點的 上一格 原點 下一格
            # 如果在範圍內 且 檢測格是255 檢查是否有鄰居是背景
            if 0 <= y < h and binary_mask[y, next_x] == 255:
                is_edge = False
                for dy_neighbor in [-1, 1]:  # 檢測格的上一格 下一格
                    ny = y + dy_neighbor
                    if 0 <= ny < h:
                        # 是背景 is_edge = True
                        if binary_mask[ny, next_x] == 0:
                            is_edge = True
                            break
                if is_edge:
                    edge_points.append((next_x, y))
                    current_x, current_y = next_x, y
                    found = True
                    break

        if not found:
            break

    return edge_points


def Connect_breakpoints(b_mask, average_range, dist_thresh=20):
    skeleton_map, skeleton = get_skeleton_map(b_mask)

    # 取細線化的點坐標
    sk_points_unique_x, _ = get_skeleton_point(skeleton_map)

    # 找端點
    kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], np.uint8)
    neighbors = cv2.filter2D(skeleton.astype(np.uint8), -1, kernel)
    endpoints = np.argwhere((skeleton == 1) & (neighbors == 1))
    # 計算所有端點對距離
    used_pairs = set()
    for i in range(len(endpoints)):  # 從 0 開始
        for j in range(i + 1, len(endpoints)):  # 0 以後的剩下(j 永遠比 i 大)
            p1, p2 = endpoints[i], endpoints[j]
            dist = np.linalg.norm(p1 - p2)

            if dist <= dist_thresh:
                pair_key = tuple(sorted((i, j)))
                used_pairs.add(pair_key)

                # 找 index in sorted points
                bp1_idx = np.where((sk_points_unique_x == p1).all(axis=1))[0]
                bp2_idx = np.where((sk_points_unique_x == p2).all(axis=1))[0]

                if bp1_idx.size == 0 or bp2_idx.size == 0:
                    continue

                p1_width_average, init_start_p1 = average_width_fun(points=sk_points_unique_x, broken_point_idx=bp1_idx, b_mask=b_mask, p=-1, average_range=average_range)
                p2_width_average, init_start_p2 = average_width_fun(points=sk_points_unique_x, broken_point_idx=bp2_idx, b_mask=b_mask, p=1, average_range=average_range)
                padding_width = (p1_width_average + p2_width_average) // 2

                connect_point_1 = sk_points_unique_x[bp1_idx - init_start_p1 + 1][0]
                connect_point_2 = sk_points_unique_x[bp2_idx + init_start_p2 + 1][0]

                line_position = list(bresenham(y0=connect_point_1[0], x0=connect_point_1[1],
                                               y1=connect_point_2[0], x1=connect_point_2[1], )
                                     )

                half_number_1 = padding_width // 2
                half_number_2 = padding_width - half_number_1
                for point in line_position:
                    x, y = point
                    b_mask[y - half_number_1:y, x] = 255
                    b_mask[y:y + half_number_2, x] = 255

    return b_mask


def average_width_fun(points, broken_point_idx, b_mask, p=1, average_range=50):
    upper_boundary_y = []
    lower_boundary_y = []
    for i in range(average_range):
        current_point_idx = broken_point_idx + i * p  # 負號往左
        broken_point_i = points[current_point_idx][0]

        init_y = broken_point_i[0]
        init_x = broken_point_i[1]

        upper_boundary_y.append(find_boundary_y(b_mask, init_y, init_x, -1))
        lower_boundary_y.append(find_boundary_y(b_mask, init_y, init_x, 1))

    widths = abs(np.array(upper_boundary_y) - np.array(lower_boundary_y)) + 1
    average_width = int(np.mean(widths))

    # 從端點開始找小於均值的位置，遇到大於就停
    seq = []
    search_range = range(0, len(widths))  # 從 start_idx 到 len(widths)
    for idx in search_range:
        if widths[idx] < average_width:
            seq.append(idx)
        else:
            break

    return average_width, len(seq)


def get_skeleton_map(binary_map):
    skeleton_map = np.zeros(binary_map.shape).astype("uint8")
    skeleton = skeletonize(binary_map)
    skeleton_map[skeleton] = 255

    return skeleton_map, skeleton


def get_skeleton_point(skeleton_map):
    # 取細線化的點坐標
    sk_points = np.column_stack(np.where(skeleton_map > 0))
    sk_points_sorted = sk_points[np.argsort(sk_points[:, 1])]

    _, unique_idx = np.unique(sk_points_sorted[:, 1], return_index=True)
    sk_points_unique_x = sk_points_sorted[unique_idx]

    return sk_points_unique_x, sk_points_sorted


def find_boundary_y(b_mask, start_y, x, step):
    """
        step = -1 往上找
        step =  1 往下找
    """
    if step == -1:
        line = b_mask[:start_y + 1, x][::-1]
    else:
        line = b_mask[start_y:, x]

    # 找第一個非 255 的位置(從 start_y 開始)
    first_non_white = np.argmax(line != 255)

    # 回傳最後一個白色像素的 y
    if step == -1:
        return start_y - first_non_white + 1
    else:
        return start_y + first_non_white - 1


def is_significant_peak_valley(y, idx, m, threshold=2, window=20):
    left = max(0, idx - window)
    right = min(len(y), idx + window + 1)
    neighbors = np.delete(y[left:right], idx - left)  # 去掉自己
    if m == "p":
        return (y[idx] - np.mean(neighbors)) >= threshold
    elif m == "v":
        return (int(np.mean(neighbors)) - y[idx]) >= threshold
