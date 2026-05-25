"""ROI band（detect 之後、excursion 主算法之前的 ROI 擴張與精煉）的使用者層 config。

與 paddleseg_config / diaphragm_detection_config 同級。
"""
from dataclasses import dataclass


@dataclass
class RoiBandConfig:
    # --- y_range 擴張 ---
    # detect() 找出的 (top, bottom) 上下各擴張 image_height * reserve_ratio。
    # 預設 50/955 ≈ 0.052 與原 patch_code.target_Y_range 的
    # `(default 50, 0.052=50/955)` 註解一致 —— 對 955 高的影像會擴張 50 pixel；
    # 對其他高度的影像會按比例縮放（修原版 y_dim 寫死的隱性 bug）。
    reserve_ratio: float = 0.052

    # --- enhanced_search 強化參數 ---
    # 水平切幾段獨立做變分增強（原 complementary_enhancing num_segments）。
    # 預設 1 對齊原 patch_code 實際呼叫值（並非函式 signature 預設的 3）。
    enhance_num_segments: int = 1

    # 強化後給 cv2.medianBlur 的 kernel size（原 hardcoded 5）。
    enhance_blur_kernel: int = 5

    # --- target_selection ---
    # 選擇下游 excursion 用的 mask 來源：
    #   True  = 用 paddle segmenter 結果（detection_pass1）
    #   False = 用古典 enhanced + 再 detect 結果（refined）
    use_segment_label: bool = True
