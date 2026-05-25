# CLAUDE.md — diaphragm_excursion AI Operating Contract

> 本檔是本 repo（diaphragm_excursion）的 AI 行為合約。任何 AI agent 在執行前必須完整閱讀並遵守。
> CLAUDE.md 本身受保護：AI 不可自行修改，須工程師發起 + review。
>
> **定位**：工作風格與輸出規範。專案細節不寫進來（避免每次 session token 過度消耗）。
> 進度紀錄看 `PROGRESS.md`；演算法細節看 source code 與 docstring。

---

## 1. 專案簡述

- **系統**：醫療影像 M-mode 橫膈膜 excursion 量測（DICOM → 物理量 cm）
- **Pipeline**：`input → segmentation → diaphragm_detection → roi_band → motion_curve → excursion → measurement → visualization`
- **架構分層**：`input/` `algorithm/` `config/` `visualization/` `paddleseglibs/`
- **Python**：3.8（paddle 環境）

---

## 2. 上層規範繼承

引用母 CLAUDE.md（`E:\PeterMC_Tsai\Claude Code\CLAUDE.md`）以下原則；其餘母版規則忽略（母版混雜跨專案資訊，不一律適用本 repo）：

- 醫療系統「沒有小改動」— 任何修改都可能影響資料完整性
- 最小修改原則 — 只動任務直接需要的部分；不順便重構
- Patch-first — 既有檔用 diff；新檔才整檔輸出
- 不確定就問，不猜
- DB schema / API contract / DICOM pipeline 動前先警告 + 取得明確確認

---

## 3. 工作節奏

### Confirm-then-Execute 流程（每次任務必經）

1. AI 提結構（§4 輸出格式）→ 工程師回 `確認` / `進X` / `跳過`
2. **未取得 confirm signal 不可動檔**
3. 動檔完成後做 AST parse + import smoke test
4. PROGRESS.md 更新進度 + Session 重啟接續點

### Patch 粒度

- **Step**：大主題（例：Step 7 viz 統整）
- **Patch**：Step 拆 9A / 9B / 9C...，**一次到位、可獨立 revert**
- **sub-patch**：必要時再細拆，每個都單獨提結構

---

## 4. Patch 輸出格式

每次 patch 提案六段都不可省略：

```
## 📋 分析
問題根因 / 受影響範圍 / 不變動但相關的鄰近邏輯

## 📝 修改計畫
按優先順序列步驟，每步驟說明目的

## 📁 修改檔案清單
| 檔案 | 操作 (NEW/PATCH/DELETE) | 說明 |

## 💻 程式碼變更
既有檔用 diff 格式；新檔整檔輸出

## ⚠️ 風險說明
API contract / DB schema / 演算法行為 / breaking change / 驗證指引

## 💡 建議（可選）
本次範圍外的觀察
```

---

## 5. 輸出文字規範

- **繁中為主**，code / 術語 / 函式名英文
- **設計分歧**用 `AskUserQuestion` 多選題；不自己決定關鍵架構選項
- **不確定就問**，不猜也不腦補
- **結尾簡短**：1-2 句說做了什麼、下一步候選
- **表格優先**於條列（資訊密度高、好掃讀）
- **不使用 emoji**（除非用戶要求；patch 結構標題的 📋 等保留為慣例）
- **不寫多段 docstring**；單行說明 + Args/Returns 足矣

---

## 6. 技術慣例

### 資料結構

- `dataclass` > `dict` / `tuple`
- 函式參數用 named args；不傳 5-tuple
- enum（如 `Phase`） > 字串比對

### 跨層方向（單向）

```
visualization → algorithm → config
visualization → input      → config
algorithm 不可 import visualization
config    不可 import 業務層
```

### 副作用

- `algorithm/` 層**禁** `cv2.imshow` / `plt.show` / module-level `matplotlib.use()` / global state mutation
- viz 層集中所有畫圖；algorithm 層只回傳資料
- 演算法路徑全 gray（`seq.as_gray()`）；final overlay 用 `seq.as_color()` 保留原 DCM 色標

### Dead code 處理

- 「看起來沒用」的程式碼**預設保留**（可能是 fallback / 未來重用）
- 確認跨檔 dead（所有 caller 都已刪）才能刪
- 函式級清理可在後續 patch 一併處理，避免 mid-state

---

## 7. Dev Workflow（git 規範）

### Branch 命名

- `main` 為主幹
- `feat/<scope>-<short>` — 新功能（例：`feat/sniff-segment-way`）
- `fix/<scope>-<short>` — bug fix
- `refactor/<scope>` — 重構
- `chore/<scope>` — PROGRESS / CLAUDE.md / 雜項

### Commit message 格式

```
Patch 9X: <一句總結，≤ 60 字元>

- 對應 PROGRESS.md 段
- 關鍵變更列點
```

### PR description 格式

```
## 對應 Patch
9X — <主題>

## 修改檔案
（從 PROGRESS.md 抓 patch 對應的檔案清單）

## 風險與驗證
- API / 演算法 / breaking change：有 / 無
- 驗證指引：...
```

### Git 禁忌（AI 絕不可做）

- ❌ **主動執行 `git commit` / `git push`** — commit/push 由用戶 `/commit` 指令觸發
- ❌ force push to `main`
- ❌ commit secrets（`.env`、device id、原始病患資料路徑、本機絕對路徑）
- ❌ `--amend` 已 push 的 commit
- ❌ `git rebase -i` / `git add -i`（互動式在本環境會卡）
- ❌ `git add -A` / `git add .`（必須列指定檔名）
- ❌ `--no-verify` / `--no-gpg-sign`（跳過 hooks）
- ❌ `git checkout --` / `git reset --hard` 動未 push 的修改

### AI 在 git 上能做什麼

- patch 收尾時附 commit message 建議文字
- 只讀命令：`git status` / `git diff` / `git log`
- 不執行任何 mutate 命令

---

## 8. Session 持久化

| 機制 | 路徑 | 角色 | 維護者 |
|---|---|---|---|
| **PROGRESS.md** | repo root（git tracked） | 專案進度、patch 紀錄、Session 重啟接續點 | AI 主動每 patch 更新 |
| **Claude memory** | `C:\Users\DDQ70\.claude\projects\E--PeterMC-Tsai-Claude-Code-diaphragm-excursion\memory\` | 個人偏好、跨 session 共識、未進 CLAUDE.md 的規約細節 | AI 偵測需要時寫 |

### 開新 session 第一動

1. 讀 PROGRESS.md 「Session 重啟接續點」段
2. memory 自動載入（無需手動）

### 內容分工

- PROGRESS.md：**做了什麼**、**待辦**、**驗證指引**
- memory：**怎麼合作**、**個人偏好**、**跨 session 共識**
- CLAUDE.md：**規約本身**（穩定、不常改）
- 三者**不重複**：CLAUDE.md 寫過的不進 memory；PROGRESS.md 寫過的不進 memory

---

## 9. 本檔保護

- AI **不可自行修改** CLAUDE.md
- 任何修改須工程師發起，AI 只能依工程師指示動筆
- 修改後需更新 §1 簡述、§2 上層規範、§6 跨層方向以對齊現況
- 大改動建議在 PROGRESS.md 留變更紀錄

---

## 10. 文件治理

### 10.1 三層分類

| Tier | 例子 | 變動頻率 | 維護者 |
|---|---|---|---|
| **STABLE** | `CLAUDE.md` | 低（規約變更才動）| 工程師 review |
| **LIVING** | `PROGRESS.md` | 高（每 patch 收尾）| AI 主動 |
| **SNAPSHOT** | `docs/notes/*.md` | 中（被引用 code 變動才更新）| 觸發者主動 |

### 10.2 SNAPSHOT 文件 header 規範

每份 `docs/notes/*.md` 必須含元資料表：

- **最後更新**（必）：`YYYY-MM-DD` 格式，每次修改 bump
- **版本**（選）：semver 風格 `0.M` / `1.0`；**只在結構性變動時 bump**（typo / 排版修正不必）
- 校對對象（具體檔案 / 模組路徑）
- 狀態（`snapshot` / `living` / `stale`）
- 過期條件（什麼變動觸發更新）

末段必含 §N 變更紀錄表：日期 / 版本 / 變更 / 動因（版本欄無 bump 時留 `—`）。

詳細 markdown 格式規範見 [`docs/STYLE.md`](docs/STYLE.md)。

### 10.3 AI 同步觸發條件

Patch 動到的 code 若被 SNAPSHOT 文件引用（例如 config 預設值、函式簽名），patch 提案的「📁 修改檔案清單」**必須**包含同步更新的 SNAPSHOT 文件。

延後修的情況：在 PROGRESS.md「待辦」記 `[ ] sync docs/X.md with code`。

### 10.4 INDEX 文件

`docs/notes/` 累積 ≥ 3 份 SNAPSHOT 後建 `docs/INDEX.md` 列表（文件 / Tier / 狀態 / 範圍）。目前未達門檻，不建。

### 10.5 里程碑 review

每次階段收尾 / git tag release，所有 SNAPSHOT 文件 header 狀態過一次（單獨 task）。

---

## 文件維護

| 項目 | 說明 |
|---|---|
| 版本 | v1.2 |
| 建立 | 2026-05-22（Step 7 收尾後） |
| 適用 | 本 repo 內所有 AI agent |
| 更新條件 | patch 流程變更 / 架構分層調整 / 新規約收斂 |
| 更新方式 | 工程師發起 PR + review |

## 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-22 | v1.0 | 初版 | Step 7 收尾後規約收斂 |
| 2026-05-23 | v1.1 | + §10 文件治理（Tier-based + SNAPSHOT header 規範） | 配合 `pre-ratio audit` 文件落地，定義跨文件同步機制 |
| 2026-05-24 | v1.2 | §10.2 SNAPSHOT 版號改雙軌（Last Updated 必 + semver 選）；§10.2 連結 `docs/STYLE.md` | 新增 STYLE.md 統一格式；降低 SNAPSHOT 同步成本 |
