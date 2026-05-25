# STYLE.md — diaphragm_excursion Documentation Style Guide

> 本檔定義本 repo 所有 markdown 文件的撰寫規範。
> 適用範圍：`CLAUDE.md` / `PROGRESS.md` / `README.md` / `ARCHITECTURE.md` / `docs/*.md` / `docs/notes/*.md`。
> Tier 分類與 SNAPSHOT 同步規則見 `CLAUDE.md` §10。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | STABLE |
| 版本 | v1.0 |
| 最後更新 | 2026-05-24 |
| 適用 | 所有 markdown 作者（含 AI agent） |

---

## §1 文件結構

每份 markdown 文件遵循以下骨架（依 tier 微調）：

```
1. H1 標題           # 開頭，每檔唯一
2. 一句定位          > blockquote
3. 元資料表          STABLE / SNAPSHOT 必填
4. ---               分隔線
5. 內容章節          ## §N
6. 變更紀錄表        SNAPSHOT 必填、STABLE 可選
```

LIVING 文件（`PROGRESS.md`）跳過元資料表，內容組織彈性，**但仍須有 H1 標題與一句定位**。

---

## §2 標題層級與 §N 編號

| Level | 用途 |
|---|---|
| **H1** `#` | 文件標題；每檔唯一 |
| **H2** `##` | 章節，前綴 `§N` |
| **H3** `###` | 子章節，前綴 `§N.M` |
| **H4** `####` | 子子章節；**盡量避免**，超過此深度考慮重組結構 |

`§N` 前綴用於章節而非附屬區塊（元資料表 / 變更紀錄）。
範例：`## §1 文件結構` → 引用作 `STYLE.md §1` 或 markdown link。

---

## §3 字型與 Markdown 渲染

Markdown 本身不規定字型；viewer（IDE / browser / preview）控制。語法統一如下：

| 語法 | 用途 |
|---|---|
| `` `inline code` `` | code 符號、檔案路徑、欄位 / 函式名、command |
| ` ```python ` | block code；**標註語言**（python / bash / diff / json） |
| `**bold**` | key term 首次出現、決策結論、警告 |
| `*italic*` | 外文詞、學術引用、強調概念 |
| `~~strikethrough~~` | 棄用內容（保留歷史） |

不混用 `***bold italic***`；不長段落粗體（粗體用於 key word 不是整段）。

**Viewer 字型建議**：等寬 + 支援 CJK（如 Sarasa Mono SC / Noto Sans Mono CJK / Cascadia Code）。

---

## §4 表格與列表

- **表格優先於列表**（資訊密度高、好掃讀）
- 列表深度最多 2 層；更深考慮拆表
- 表格欄超過 5 欄考慮拆兩個或改用列表
- markdown source **不強求對齊**（render 後自動處理；過度對齊增加 edit 成本）

---

## §5 元資料表規範

STABLE / SNAPSHOT 文件 header 必含元資料表（H1 + blockquote 後直接放）：

| 欄位 | STABLE | SNAPSHOT | LIVING | 說明 |
|---|---|---|---|---|
| **Tier** | 必 | 必 | — | STABLE / LIVING / SNAPSHOT |
| **版本** | 必 | **選** | — | semver `vN.M` (STABLE) / `0.M` (SNAPSHOT) |
| **最後更新** | 必 | **必** | — | `YYYY-MM-DD` 格式，每次修改 bump |
| **適用** | 必 | 必 | — | 受眾或範圍 |
| **校對對象** | — | 必 | — | 引用的 code 範圍 |
| **狀態** | — | 必 | — | `snapshot` / `living` / `stale` |
| **過期條件** | — | 必 | — | 什麼變動觸發更新 |

**SNAPSHOT 版號雙軌**（per `CLAUDE.md` §10.2）：
- **最後更新** 必填，每次修改都要 bump 日期
- **版本** 選填，只在結構性變動時 bump（typo / 排版修正不必 bump）

---

## §6 變更紀錄表規範

文末最後一節 `## §N 變更紀錄`：

```markdown
| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| YYYY-MM-DD | x.y | <一句總結> | <為什麼改> |
```

**入表規則**：

| 變動類型 | 是否入表 |
|---|---|
| 結構性變動（加 / 刪 / 改章節） | 必入 |
| 內容修正（含 typo） | 視變動量決定 |
| 排版調整 | 不必入 |

**版本欄留空**：若採 SNAPSHOT 雙軌且當次無版號 bump，版本欄留 `—`。

---

## §7 路徑與引用

| 引用對象 | 語法 |
|---|---|
| 檔案路徑 | `` `algorithm/excursion/brightness.py` `` |
| 跨文件連結 | `[檔名](relative/path.md)` |
| 段落引用 | `[§N 標題](#n-標題)` 或文字「見 CLAUDE.md §3」 |
| 外部 URL | `[文字](https://...)` |
| Issue / PR | `[#NN](https://github.com/.../issues/NN)`（上 git 後使用） |

---

## §8 語言與術語

| 維度 | 規則 |
|---|---|
| **主語言** | 繁中為主 |
| **保留英文** | code / 函式名 / 變數名 / dataclass field / 套件名 / code 註解的英文部分 |
| **數字** | 半形 |
| **中文段落標點** | 全形（。，；：「」） |
| **code / 英文段落標點** | 半形 |
| **混合行** | 中英穿插時標點隨主語言；專有名詞英文用半形 |

---

## §9 圖片與圖表

| 維度 | 規則 |
|---|---|
| **位置** | `docs/img/` |
| **命名** | `<doc_name>_<topic>_<seq>.png`（如 `architecture_pipeline_01.png`） |
| **格式** | PNG（圖示）/ SVG（向量圖，git 可 diff） |
| **引用** | `![alt text](docs/img/file.png)` |
| **大圖** (> 500 KB) | 考慮壓縮或外部連結 |
| **圖內文字** | 英文為主（避免字型相依） |

---

## §10 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | v1.0 | 初版建立；§1-§9 規範定義 | 統一文件格式，配合「文件化目前專案」需要 |
