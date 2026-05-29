# diaphragm_excursion

> M-mode 超音波橫膈膜 excursion 自動量測管線：DICOM → motion curve → peak/trough → 物理距離（cm）。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-25 |
| 適用 | 接手工程師、新加入 AI agent、回顧自己進度 |

---

## §1 專案簡述

兩層架構：

- **Input 層**：DICOM / PNG → 統一 `FrameSequence`（含 N×H×W frames、metadata、scale_x/y）
- **Algorithm 層**：segmentation → diaphragm_detection → ROI band → motion_curve → excursion → measurement
- **Visualization 層**：debug per-stage + final overlay（兩條獨立 track）

**技術棧**：

| 維度 | 內容 |
|---|---|
| Python | 3.8 |
| 核心依賴 | `paddleseg`（vendored）/ `pydicom` / `numpy` / `scipy` / `scikit-image` / `opencv-python` / `Pillow` / `pywt` / `bresenham` |
| 影像來源 | DICOM single-frame / multi-frame；PNG single / dir |
| 輸出 | excursion 物理距離（cm）+ 可選 viz overlay PNG |

---

## §2 現況

| 維度 | 狀態 |
|---|---|
| Refactor 進度 | Step 1-9 完成；Step 10（Multi-frame Mode 1）進行中 |
| Git | 尚未 `git init`（refactor 收尾後 + Step 9 實機驗證後上 git） |
| 等待驗證 | Step 9 ratio 化（Patch 10A/B/C）2026-05-25 週一實機跑 main.py 驗證 byte-identical |
| 待續 | Patch 11B（拼接邏輯）設計已 backup 在 `docs/notes/patch_11b_design_backup.md`，等 user 確認執行 |

詳細狀態與里程碑見 [`PROGRESS.md`](PROGRESS.md)。

---

## §3 Quick Start

### 環境

需要 Python 3.8 + paddle 安裝環境（含 vendored `paddleseglibs/`）。

### 取得模型權重

`paddleseglibs/output/model/*/best_model/model.pdparams`（5 × 323 MB）**未入 git**（.gitignore 排除）。

clone 後請另外取得：

- 路徑：`paddleseglibs/output/model/<model_name>/best_model/model.pdparams`
- 來源：自 Paddle model zoo 或內部 lab 儲存
- 預設 cfg 走 `paddleseglibs.predict.DEFAULT_MODEL_PATH`；如改路徑請同步 `PaddleSegSegmenterConfig.model_path`

缺模型 → main.py 跑到 segmenter.load() 會報錯。

### 編輯 DCM 路徑

`main.py` 末尾預設值：

```python
image_path = (
    r"E:\PeterMC_Tsai\Diaphragm_data\Quality_Classification_base_up_down\Dicom_ex"
    r"\Excursion-QB\1017(new))\Peter\Peter_Quiet_1.dcm"
)
run(image_path)
```

改為自己 DCM 路徑後執行：

```bash
python main.py
```

### 預期 log

每 10 frame 印一行：

```
[input] source_type=dcm_multi, frames.shape=(N, H, W), fps=...
[preprocess] cropped frames.shape=(N, H, W)
[frame 1/N] best=(top, bottom), y_band=(min, max), source=segment/classical, target=True, broken=K, batches=B, excursion_cm=X.XX
...
[done] N frames, target_binary=N, excursion_runs=M
```

`excursion_cm` 合理範圍：橫膈膜典型 1–7 cm。

### 開啟 viz

預設不存圖。手動把 `main.py` 內這行：

```python
viz_cfg = VisualizationConfig()
```

改成：

```python
viz_cfg = VisualizationConfig(enabled=True, save_final=True, save_debug=True)
```

輸出位置：

- `output/final/{i:04d}.png` — 綜合成果圖（crest/trough marker + excursion_cm 文字 + motion curve 軌跡）
- `output/debug/{stage}/{i:04d}.png` — 9 個 stage 各自目錄（detection / motion / excursion brightness 波形 / 等）

---

## §4 Repo 結構

```
diaphragm_excursion/
├── main.py                          orchestration（per-frame loop）
├── CLAUDE.md                        AI 行為合約（STABLE）
├── PROGRESS.md                      進度紀錄（LIVING）
├── algorithm/
│   ├── diaphragm_detection/         橫膈膜 ROI 偵測
│   ├── excursion/                   peak/trough 找峰算法 + 物理量計算
│   ├── motion_curve/                時間軸軌跡擷取
│   ├── multiframe/                  Multi-frame 模式（Step 10 進行中）
│   ├── roi_band/                    ROI 擴張 + enhanced search
│   ├── segmentation/                PaddleSegSegmenter wrapper
│   ├── signal_processing/           wavelet 等 signal helpers
│   └── frame_result.py              FrameResult dataclass（每 frame 整合）
├── config/                          所有 dataclass config（per-layer）
├── input/                           DCM/PNG reader + FrameSequence
├── visualization/                   debug 與 final overlay viz
├── paddleseglibs/                   vendored PaddleSeg（含 Patch 2A-2C 改動）
├── docs/
│   ├── STYLE.md                     文件格式規範（STABLE）
│   └── notes/                       SNAPSHOT 文件
├── experiments/                     驗證 script
├── font/                            自訂字型（viz 用 Altinn-DIN Bold.otf）
└── output/                          viz 輸出（gitignored）
```

---

## §5 文件索引

完整 14 份文件清單見 [`docs/INDEX.md`](docs/INDEX.md)（依 Tier 分組、含 SNAPSHOT 狀態 audit）。

新人優先看：

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — 跨層架構與設計決策
- [`docs/pipeline.md`](docs/pipeline.md) — per-frame data flow
- [`docs/modules/`](docs/modules/) — 各 layer 內部設計（algorithm / input / visualization）
- [`CLAUDE.md`](CLAUDE.md) — AI 行為合約（協作慣例）
- [`PROGRESS.md`](PROGRESS.md) — 進度紀錄 / Session 重啟接續點

---

## §6 已知限制

| 限制 | 影響 | 處理 |
|---|---|---|
| Multi-frame DCM Mode 1 拼接未整合 | 多 frame DCM 跑出來會是「per-frame 跑 single-frame algo」N 份結果，沒有 global 拼接 | Patch 11B/11C 進行中 |
| PaddleSeg 環境依賴重 | `python main.py` 必須在 paddle env 跑 | vendored `paddleseglibs/`；env 設定靠使用者 |
| 無 unit test 套件 | 驗證靠 `main.py` log 對照預期 | `experiments/verify_segmenter_equivalence.py` 為單一驗證 script |
| 無 git tag / version | 無正式版本標記 | 待 refactor 收尾後 git init + tag |
| `area_ratio` numerator hardcode | `DiaphragmDetectionConfig.area_ratio = 10000 / (955 * 1500)`：分子 10000 是 canonical pixel 數，異尺寸 input 邏輯仍正確但設計史不明顯 | `docs/notes/size_normalization_pre_ratio_audit.md` §2.3 已標 |

---

## §7 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§6 全部章節定義 | 文件化專案啟動，提供 onboarding 入口 |
| 2026-05-24 | — | §5 文件索引簡化：移除全表，改連 `docs/INDEX.md` + 列「新人優先看」5 條 | INDEX.md 已成為單一真實來源；避免兩處索引 sync 麻煩 |
| 2026-05-25 | — | §3 加「取得模型權重」子節；.gitignore 排除 paddleseglibs/output/ 與 paddle artifacts | 首次 git commit 前 pre-cleanup；1.7GB 模型權重不入 git |
