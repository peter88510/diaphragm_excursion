# input/ — 輸入層

> DICOM / PNG → 統一 `FrameSequence` 格式。
> 跨層架構見 [`ARCHITECTURE.md`](../../ARCHITECTURE.md)；資料流順序見 [`docs/pipeline.md`](../pipeline.md) §2。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 改 input 邏輯時參考；新人理解資料來源 |

---

## §1 模組目標

把 DCM single-frame / multi-frame、PNG 單檔 / 資料夾**四種來源**統一為 `FrameSequence`，下游演算法只看一種型別。

設計取捨：

- **reader 只負責讀**：不 resize、不轉色彩空間、不塞 PhysicalDelta 預設值（避免多裝置場景默默算錯）
- **frames 首維永遠是 N**：single-frame 也包成 `N=1`，下游 `for i, frame in enumerate(seq.frames)` 一致
- **metadata 用 dict**：彈性容納不同 source 的欄位差異（DCM 有 PhysicalDelta，PNG 沒有）

---

## §2 子結構

```
input/
├── __init__.py            re-export: load / apply_dicom_crop / FrameSequence
├── loader.py              load(path) 對外入口；依路徑類型分派
├── frame_sequence.py      FrameSequence dataclass + as_gray / as_color
├── readers/
│   ├── __init__.py
│   ├── dicom_reader.py    DICOM single / multi 統一處理
│   └── png_reader.py      PNG 單檔 / 資料夾
└── preprocessing/
    └── dicom_crop.py      apply_dicom_crop（套 region_location 裁切）
```

---

## §3 對外 API

```python
from input import load, apply_dicom_crop, FrameSequence

seq = load(path)                    # path 是 .dcm / .png / 資料夾
seq = apply_dicom_crop(seq)         # DCM 才有效；其他來源 no-op
gray_frames = seq.as_gray()         # (N, H, W)
color_frames = seq.as_color()       # (N, H, W, 3)
```

caller **不需要**判斷檔案類型，也不需要認識個別 reader 模組。

---

## §4 `FrameSequence` 設計

### 欄位

| 欄位 | 型別 | 說明 |
|---|---|---|
| `frames` | `np.ndarray` | shape `(N, H, W)` 或 `(N, H, W, 3)` |
| `source_type` | `str` | 4 種：`'dcm_single'` / `'dcm_multi'` / `'png_file'` / `'png_dir'` |
| `source_path` | `str` | 原始檔案或資料夾路徑 |
| `fps` | `Optional[float]` | multi-frame DCM 才有意義（從 `RecommendedDisplayFrameRate` 或 `CineRate`） |
| `metadata` | `dict` | 彈性欄位（見下方） |

### shape 約束（`__post_init__` 驗證）

- `frames.ndim` 必須是 3 或 4
- `ndim==4` 時通道維必須是 1 / 3 / 4
- 違反 → raise `ValueError`

### `as_gray()` / `as_color()`

| Method | 灰階 source | 彩色 source |
|---|---|---|
| `as_gray()` | 直接 return frames（zero-copy） | `cv2.cvtColor(BGR2GRAY)` 逐 frame |
| `as_color()` | `np.stack([frames]*3, axis=-1)`（3 通道複製） | 直接 return frames（zero-copy） |

`is_color` property：`frames.ndim == 4 and frames.shape[-1] >= 3`。

### `metadata` 約定

| Key | 來源 | 用途 |
|---|---|---|
| `physical_delta_y` | DCM `SequenceOfUltrasoundRegions[1].PhysicalDeltaY` | cm/pixel，給 `compute_peak_info(scale_y=...)` |
| `physical_delta_x` | DCM `SequenceOfUltrasoundRegions[1].PhysicalDeltaX` | sec/pixel，sniff phase 用 |
| `region_location` | DCM region `RegionLocationMin/MaxX0/Y0/X1/Y1` | `apply_dicom_crop` 用 |
| `image_paths` | PNG dir | 排序後的檔案路徑 list |

PNG source `metadata` 預設只有 `image_paths`（dir 模式）；**PhysicalDelta 缺，caller 需顯式提供**。

---

## §5 Reader Dispatch

### `load(path)` 邏輯（`loader.py`）

```python
if os.path.isdir(path):
    return png_reader.read_directory(path)
if not os.path.isfile(path):
    raise FileNotFoundError(...)
ext = splitext(path)[1].lower()
if ext in ('.dcm', '.dicom'):
    return dicom_reader.read(path)
if ext in ('.png', '.jpg', '.jpeg', '.bmp'):
    return png_reader.read_file(path)
raise ValueError(...)
```

### `dicom_reader.read(dcm_path)`

| 行為 | 細節 |
|---|---|
| **single/multi 偵測** | `getattr(dcm, 'NumberOfFrames', 1) > 1` |
| **shape 標準化** | single `(H,W)` → `(1,H,W)`；multi 直接信任 pydicom 慣例首維 N |
| **`source_type`** | `'dcm_single'` / `'dcm_multi'` |
| **fps** | multi-frame：`RecommendedDisplayFrameRate` > `CineRate`；single：None |
| **metadata** | 取 `SequenceOfUltrasoundRegions[_REGION_INDEX]` 的 PhysicalDelta + RegionLocation |

#### Domain note：`_REGION_INDEX = 1`

DCM 上半 B-mode、下半 M-mode：
- `SequenceOfUltrasoundRegions[0]` = B-mode（2D 影像）
- `SequenceOfUltrasoundRegions[1]` = **M-mode**（時間軸掃描，excursion 計算用）

故 `_REGION_INDEX = 1`。

### `png_reader.read_file(png_path)`

```
img = cv2.imread(png_path)              # BGR, (H, W, 3)
frames = img[np.newaxis, ...]           # (1, H, W, 3)
source_type = 'png_file'
metadata = {}                            # PhysicalDelta 不塞預設值
```

### `png_reader.read_directory(dir_path)`

| 行為 | 細節 |
|---|---|
| **檔案搜集** | `os.walk(dir_path)`，遞迴 |
| **過濾規則** | 跳過 `.ipynb_checkpoints/`；跳過含 `label` 的子資料夾；只收 `.png/.jpg/.jpeg/.bmp` |
| **排序** | `natsorted`（自然數字排序） |
| **堆疊** | `np.stack` → `(N, H, W, 3)`；各 frame 尺寸不一致則 `raise ValueError` |
| **source_type** | `'png_dir'` |
| **metadata** | `{'image_paths': image_paths}` |

---

## §6 preprocessing — `apply_dicom_crop`

| 維度 | 內容 |
|---|---|
| **入口** | `apply_dicom_crop(seq, ruler=40, black_padding=50) → FrameSequence` |
| **觸發** | `seq.metadata` 含 `region_location` 才動；其他 source pass-through |
| **shape 處理** | 只 slice H/W；N 維永遠保留（修原 multi-frame 被切空 bug） |

### 裁切座標公式

```
y_start = region_location.min_y0 + ruler
y_end   = region_location.max_y1 + 1
x_start = region_location.min_x0 + black_padding + ruler
x_end   = region_location.max_x1 + black_padding + 1
```

`ruler` 與 `black_padding` 預設與原 main.py 一致；空集 crop（`cropped.size == 0`）會 raise。

### 為何 metadata 解耦 pydicom

原版 `CropProcess` 直接吃 pydicom Dataset 物件；新版只依賴 `seq.metadata['region_location']` 字典。

優點：
- preprocessing 不依賴 pydicom（可用於非 DCM 但有等價 metadata 的 source）
- 純資料轉換更容易測試 / mock

---

## §7 依賴方向

```
input/                       外部依賴
├── loader.py            →   readers/*
├── frame_sequence.py    →   cv2, numpy (channel 轉換用)
├── readers/dicom_reader →   pydicom
├── readers/png_reader   →   cv2, natsort
└── preprocessing/...    →   (純 numpy)

被依賴：
  main.py                →   input.load / input.apply_dicom_crop
  algorithm/*            →   input.FrameSequence (型別 hint)
  visualization/*        →   input.FrameSequence (final overlay base canvas)
```

input/ 內部**不依賴**任何 `algorithm/` 或 `config/`（純粹輸入正規化）。

---

## §8 待辦與已知限制

| 項目 | 影響範圍 | 處理計畫 |
|---|---|---|
| PNG 預設 `PhysicalDeltaY/X` config 化 | PNG source 必須 caller 顯式提供刻度；否則 `compute_peak_info` 拿不到 scale_y | TODO（未來引入 `PngInputConfig` 或從 EXIF 抽？） |
| PNG resize 目標尺寸 hardcode 在 algorithm 層 | 原 `(1500, 955)` 已從 reader 移除；algorithm 層仍假設 canonical 尺寸 | Step 9 ratio 化大部分解決；剩餘細部見 audit doc |
| Multi-frame DCM 存檔覆蓋 bug | paddle segmenter 路徑下 N 個 mask 寫到同一 PNG | 暫不修；測試流程不依賴存檔 |
| PNG dir 各 frame 尺寸不一致 | `np.stack` raise | 預期由 caller 確保資料一致 |
| `SequenceOfUltrasoundRegions[1]` 是否永遠 M-mode | 不同設備 DCM 結構可能不同 | 目前驗證範圍內 OK；多設備時可能需 region detection |

---

## §9 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§8 全部章節定義 | 文件化專案，深入 input 內部 |
