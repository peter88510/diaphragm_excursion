# docs/INDEX.md — Documentation Index

> repo 全 markdown 文件索引，依 Tier 分組。
> 用途：找文件、查 SNAPSHOT staleness 狀態。
> Tier 定義見 [`CLAUDE.md`](../CLAUDE.md) §10；格式規範見 [`STYLE.md`](STYLE.md)。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 全文件導航、SNAPSHOT 狀態 audit |

---

## §1 STABLE 文件

長期穩定、規約 / 設計層級。

| 文件 | 路徑 | 版本 | 最後更新 | 用途 |
|---|---|---|---|---|
| [README.md](../README.md) | repo root | v1.0 | 2026-05-24 | Onboarding 入口、快速上手 |
| [CLAUDE.md](../CLAUDE.md) | repo root | v1.2 | 2026-05-23 | AI 行為合約、patch 流程、git 禁忌 |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | repo root | v1.0 | 2026-05-24 | 跨層架構、模組責任、設計決策 |
| [STYLE.md](STYLE.md) | `docs/` | v1.0 | 2026-05-24 | markdown 文件格式規範 |
| [pipeline.md](pipeline.md) | `docs/` | v1.0 | 2026-05-24 | per-frame data flow 對照 |
| [modules/algorithm.md](modules/algorithm.md) | `docs/modules/` | v1.0 | 2026-05-24 | `algorithm/` 內部結構與 sub-package |
| [modules/input.md](modules/input.md) | `docs/modules/` | v1.0 | 2026-05-24 | `input/` 內部結構與 reader dispatch |
| [modules/visualization.md](modules/visualization.md) | `docs/modules/` | v1.0 | 2026-05-24 | `visualization/` 內部結構與兩 track 設計 |
| [INDEX.md](INDEX.md) | `docs/` | v1.0 | 2026-05-24 | 本檔 |

---

## §2 LIVING 文件

跟隨 patch 進度持續更新，無版號。

| 文件 | 路徑 | 用途 |
|---|---|---|
| [PROGRESS.md](../PROGRESS.md) | repo root | 階段進度、待辦、Session 重啟接續點 |

---

## §3 SNAPSHOT 文件

時間點快照；版本選填、最後更新必填；header 含「狀態 / 過期條件」。

| 文件 | 版本 | 最後更新 | 狀態 | 校對對象 / 範圍 |
|---|---|---|---|---|
| [notes/size_normalization_pre_ratio_audit.md](notes/size_normalization_pre_ratio_audit.md) | 0.4 | 2026-05-23 | snapshot | `algorithm/` `config/` 內所有 size-sensitive 預設值；含 Step 9 ratio 化進度 |
| [notes/patch_11b_design_backup.md](notes/patch_11b_design_backup.md) | 0.3 | 2026-05-25 | implemented | `algorithm/multiframe/global_window.py`（已落地，含 11B' 兩段 stitching）；保留作設計史 |
| [notes/model_load_caching.md](notes/model_load_caching.md) | 0.1 | 2026-05-24 | snapshot | `algorithm/segmentation/paddleseg_segmenter.py`、`paddleseglibs/paddleseg/core/predict.py` 的 `skip_model_load` 旗標 |
| [api_reference.md](api_reference.md) | 0.8 | 2026-05-29 | snapshot | `config/*.py`、`algorithm/**/*.py`、`input/**/*.py`、`visualization/**/*.py` 的欄位 / 簽名 |

---

## §4 維護指引

### 何時更新 INDEX

| 觸發事件 | INDEX 動作 |
|---|---|
| 新增 STABLE / SNAPSHOT 文件 | 加一列 |
| SNAPSHOT 版本 bump | 更新版本欄與「最後更新」 |
| SNAPSHOT 狀態變 `stale` | 更新狀態欄；考慮在 PROGRESS.md 加待辦 |
| 文件搬位置 / 改檔名 | 更新路徑連結 |

### staleness audit

定期（每階段收尾 / git tag release）掃過 §3 表，確認：

- 「校對對象」欄列的 code 是否仍存在
- 「狀態」欄是否仍是 `snapshot`（已被新 patch 改過頭就標 `stale`）

---

## §5 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§4 全部章節 + 12 份文件對照表 | CLAUDE.md §10.4 觸發（SNAPSHOT ≥ 3 份） |
| 2026-05-24 | — | §3 加 `api_reference.md`（SNAPSHOT 0.1） | 進階文件化第 4 份 doc 落地 |
| 2026-05-25 | — | `api_reference.md` 0.1 → 0.2；Last Updated bump | Patch 12A：cfg 結構整理連動 SNAPSHOT 同步 |
| 2026-05-25 | — | `api_reference.md` 0.2 → 0.3；`patch_11b_design_backup.md` 0.1 → 0.2 標 implemented | Patch 11B 邏輯落地連動 SNAPSHOT 同步 |
| 2026-05-25 | — | `api_reference.md` 0.3 → 0.4；`patch_11b_design_backup.md` 0.2 → 0.3 | Patch 11B'：兩段 stitching 連動 SNAPSHOT 同步 |
| 2026-05-25 | — | `api_reference.md` 0.4 → 0.5；§3.9 加 `render_global_final` | Patch 11C-GW + 11D：main.py dispatch + global final viz |
| 2026-05-25 | — | `api_reference.md` 0.5 → 0.6；§1.9 新增 `DicomCropConfig` | Patch 13A：dicom_crop 參數抽至 config |
| 2026-05-25 | — | `api_reference.md` 0.6 → 0.7；§3.6 加 `aggregate_measurements`；§3.9 `excursion_info_display` 簽名變更 | Patch 13C：info_display 多 peak + ratio 化 + aggregator stub |
| 2026-05-29 | — | `api_reference.md` 0.7 → 0.8；REALTIME 全套（cfg / RealtimeState / ShiftResult / estimate_shift / render_realtime_*）| Patch 14A-18：REALTIME mode 端到端 |
