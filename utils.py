import cv2
import os
from natsort import natsorted

def excursion_time_calculator(crest_position, trough_position, scale_x, scale_y):
    # 位移 Excursion(unit: pixel)
    #                                                                       + 2 是上下邊界手標時預設是標邊界外
    excursion_pxl = abs(crest_position[1] - trough_position[1]) + 1 + 0  # 位移 波峰減波谷Y軸
    time_pxl = abs(crest_position[0] - trough_position[0]) + 1 + 0

    excursion_cm = round(excursion_pxl * scale_y, 2)  # cm
    time_sec = round(time_pxl * scale_x, 2)  # seconds
    velocity = round(excursion_cm / time_sec, 2)

    print("[][][] SCALE Y: {}".format(scale_y))
    return excursion_pxl, excursion_cm, time_pxl, time_sec, velocity


def FindBoundary(diaphragm_mask, selected_x_crest, selected_y_ctest, selected_x_trough, selected_y_trough):
    """
    :param diaphragm_mask:
    :param selected_x_crest:
    :param selected_y_ctest:
    :param selected_x_trough:
    :param selected_y_trough:
    :return:
    diaphragm_mask 是 包含斷掉橫膈膜 不只有target
    """
    left_ROI = min(selected_x_trough[0], selected_x_crest[0])
    right_ROI = max(selected_x_trough[0], selected_x_crest[0]) + 1
    top_ROI = min(selected_y_ctest[0], selected_y_trough[0]) - 25
    bottom_ROI = max(selected_y_ctest[0], selected_y_trough[0]) + 25

    # roi map
    roi_map = diaphragm_mask[top_ROI:bottom_ROI, left_ROI:right_ROI]

    # 對應 ROI 內座標 crest
    roi_position_c = (selected_x_crest[0] - left_ROI, selected_y_ctest[0] - top_ROI)  # (x, y)
    boundary_crest = find_boundary_v2(roi_map=roi_map,
                                      roi_position=roi_position_c, m=1)

    # 對應 ROI 內座標 trough
    roi_position_t = (selected_x_trough[0] - left_ROI, selected_y_trough[0] - top_ROI)  # (x, y)
    boundary_trough = find_boundary_v2(roi_map=roi_map,
                                       roi_position=roi_position_t, m=-1)
    # 還原原圖座標
    crest_position = (boundary_crest[0] + left_ROI, boundary_crest[1] + top_ROI)  # (x, y)
    trough_position = (boundary_trough[0] + left_ROI, boundary_trough[1] + top_ROI)  # (x, y)

    return crest_position, trough_position


def find_boundary_v2(roi_map, roi_position, m=1):
    """
    :param roi_map:
    :param m: 1 向上找波峰 -1向下找波谷
    :return:
    """
    # global top_ROI, left_ROI

    contours, hierarchy = cv2.findContours(roi_map, mode=cv2.RETR_EXTERNAL, method=cv2.CHAIN_APPROX_NONE)

    # 搜尋最大 y 值的邊界點
    max_y = m * 10000000  # 最大值或最小值
    best_point = None

    target_contour = next((contour for contour in contours if any((x, y) == roi_position for x, y in contour[:, 0])), None)

    N = 0  # roi_map.shape[1] // 2
    if target_contour is not None:
        for point in target_contour:
            x, y = point[0]
            # 限制 x 在 (x_start - N, x_start + N) 內
            if roi_position[0] - N <= x <= roi_position[0] + N:
                if y * m <= max_y * m:  # y < max_y 找到最小 y（最上面的點） y*-1 < max_y*-1 找到最大y(最底部的點)
                    max_y = y
                    best_point = (x, y)
    else:
        best_point = roi_position

    return best_point


def get_image_list(image_path):
    """Get image list"""
    valid_suffix = [
        '.JPEG', '.jpeg', '.JPG', '.jpg', '.BMP', '.bmp', '.PNG', '.png', '.dcm', '.DICOM'
    ]
    image_list = []
    image_dir = None
    if os.path.isfile(image_path):
        if os.path.splitext(image_path)[-1] in valid_suffix:
            image_list.append(image_path)
        else:
            image_dir = os.path.dirname(image_path)
            with open(image_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if len(line.split()) > 1:
                        line = line.split()[0]
                    image_list.append(os.path.join(image_dir, line))
    elif os.path.isdir(image_path):
        image_dir = image_path
        for root, dirs, files in os.walk(image_path):
            for f in files:
                if '.ipynb_checkpoints' in root:
                    continue
                if 'label' in root:
                    continue
                if os.path.splitext(f)[-1] in valid_suffix:
                    image_list.append(os.path.join(root, f))
    else:
        raise FileNotFoundError(
            '`--image_path` is not found. it should be an image file or a directory including images'
        )

    if len(image_list) == 0:
        raise RuntimeError('There are not image file in `--image_path`')

    image_list = natsorted(image_list)
    return image_list, image_dir
