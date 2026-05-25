"""Step 2 重構驗證 script。

目的：
  1. 確認新 PaddleSegSegmenter.predict() 與舊 paddleseglibs.predict.infer()
     對同一張 DICOM 的輸出 byte-identical
  2. 確認 PaddleSegSegmenter 重複 predict() 時 model weights 只 load 一次
  3. 確認多次 predict() 結果一致（同 input → 同 output）

執行方式（從 repo 根目錄）：
    python experiments/verify_segmenter_equivalence.py

預期 log 中 "Load model cost" 訊息出現次數：
    - 舊 infer() 路徑：1 次
    - 新 PaddleSegSegmenter.load()：1 次
    - 新 PaddleSegSegmenter.predict() 重複呼叫：0 次
    → 總計剛好 2 次
"""
import os
import sys

# 讓 script 可從 repo 根目錄直接執行（無需先 pip install -e .）
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import numpy as np
import pydicom

from paddleseglibs.predict import DEFAULT_MODEL_PATH


# ===== 測試資料路徑（依環境調整） =====
TEST_DCM = (
    r"E:\PeterMC_Tsai\Diaphragm_data\Quality_Classification_base_up_down"
    r"\Dicom_ex\Excursion-QB\26_0511\1776049685152\20260511\Peter_Quiet_1.dcm"
)
# 引用 paddleseglibs 的權威預設值（module-anchored 絕對路徑，與 cwd 無關）。
# 若要測試其他模型權重，直接覆寫這個常數即可。
MODEL_PATH = DEFAULT_MODEL_PATH


def crop_dicom_frame(dcm_path):
    """重現 main.py 的 CropProcess(crop=True) 以確保兩條路徑吃同樣輸入。"""
    dcm = pydicom.dcmread(dcm_path)
    frame = dcm.pixel_array
    region = dcm.SequenceOfUltrasoundRegions[1]
    ruler = 20
    black_padding = 0
    cut = frame[
        region.RegionLocationMinY0 + ruler:region.RegionLocationMaxY1 + 1,
        region.RegionLocationMinX0 + black_padding + ruler:
        region.RegionLocationMaxX1 + black_padding + 1,
        :,
    ]
    return cut


def run_old_path(image_path, dcm_array):
    """走舊 paddleseglibs.predict.infer() (compat shim)。

    NOTE: infer() 內部呼叫 parse_args() 會讀 sys.argv，這裡先把 argv 縮成
    只有 script 名稱，避免本驗證 script 自己的參數污染 argparse。
    """
    saved_argv = sys.argv
    sys.argv = [sys.argv[0]]
    try:
        from paddleseglibs.predict import infer
        return infer(
            image_list=[image_path],
            image_dir=os.path.dirname(image_path),
            dcm_array=dcm_array,
            model_path=MODEL_PATH,
        )
    finally:
        sys.argv = saved_argv


def build_new_segmenter():
    """建立 PaddleSegSegmenter；save_predictions=True 以對齊舊路徑寫檔行為。

    （我們比的是回傳 PIL Image，寫不寫檔不影響結果；對齊只是為了讓 log 與
    side-effect 一致，方便目測比對。）
    """
    from algorithm.segmentation import PaddleSegSegmenter
    from config.paddleseg_config import PaddleSegSegmenterConfig

    cfg = PaddleSegSegmenterConfig(
        model_path=MODEL_PATH,
        save_predictions=True,
    )
    segmenter = PaddleSegSegmenter(cfg)
    segmenter.load()
    return segmenter


def compare_pil(old, new, label):
    print(f"  [{label}] old: mode={old.mode}, size={old.size}")
    print(f"  [{label}] new: mode={new.mode}, size={new.size}")
    if old.mode != new.mode or old.size != new.size:
        print(f"  ❌ mode/size mismatch")
        return False

    old_arr = np.array(old)
    new_arr = np.array(new)
    if np.array_equal(old_arr, new_arr):
        print(f"  ✅ byte-identical mask arrays ({old_arr.shape}, dtype={old_arr.dtype})")
        return True

    diff_pixels = int((old_arr != new_arr).sum())
    total = int(old_arr.size)
    print(f"  ❌ arrays differ at {diff_pixels}/{total} pixels ({diff_pixels/total:.2%})")
    return False


def main():
    if not os.path.isfile(TEST_DCM):
        print(f"❌ Missing test DICOM: {TEST_DCM}")
        return 1
    if not os.path.isfile(MODEL_PATH):
        print(f"❌ Missing model file: {MODEL_PATH}")
        return 1

    print(f"[setup] DICOM: {TEST_DCM}")
    dcm_array = crop_dicom_frame(TEST_DCM)
    print(f"[setup] cropped shape: {dcm_array.shape}, dtype: {dcm_array.dtype}")

    print("\n========== [1] OLD infer() path ==========")
    old_mask = run_old_path(TEST_DCM, dcm_array)

    print("\n========== [2] NEW PaddleSegSegmenter (load + first predict) ==========")
    segmenter = build_new_segmenter()
    new_mask_1 = segmenter.predict(TEST_DCM, dcm_array=dcm_array)

    print("\n========== [3] Byte-identical compare (old vs new #1) ==========")
    ok_old_vs_new = compare_pil(old_mask, new_mask_1, "old vs new#1")

    print("\n========== [4] Re-use segmenter — NO model re-load expected ==========")
    new_mask_2 = segmenter.predict(TEST_DCM, dcm_array=dcm_array)
    new_mask_3 = segmenter.predict(TEST_DCM, dcm_array=dcm_array)
    ok_12 = compare_pil(new_mask_1, new_mask_2, "new#1 vs new#2")
    ok_13 = compare_pil(new_mask_1, new_mask_3, "new#1 vs new#3")

    print("\n========== [5] 檢查 log 中 'Load model cost' 出現次數 ==========")
    print("  預期：恰好 2 次（舊 infer() 1 次 + 新 load() 1 次）")
    print("  若新的 predict() 也印出 'Load model cost'，代表 skip_model_load 未生效")

    print("\n========== Summary ==========")
    all_ok = ok_old_vs_new and ok_12 and ok_13
    print(f"  old vs new#1     : {'PASS' if ok_old_vs_new else 'FAIL'}")
    print(f"  new#1 vs new#2   : {'PASS' if ok_12 else 'FAIL'}")
    print(f"  new#1 vs new#3   : {'PASS' if ok_13 else 'FAIL'}")
    print(f"  Overall          : {'✅ PASS' if all_ok else '❌ FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
