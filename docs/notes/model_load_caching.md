# Model Load Caching — 學習筆記

> 紀錄 Step 2 重構解決「model 每次呼叫都重 load」問題的設計思考。
> 本文目的：理解問題本質、解法光譜、為什麼選定 class-based lifecycle。

---

## 文件元資料

| 項目 | 值 |
|---|---|
| Tier | SNAPSHOT |
| 版本 | 0.1 |
| 最後更新 | 2026-05-24 |
| 校對對象 | `algorithm/segmentation/paddleseg_segmenter.py`、`paddleseglibs/paddleseg/core/predict.py`（`skip_model_load` 旗標） |
| 狀態 | snapshot |
| 過期條件 | `PaddleSegSegmenter` 介面或 `skip_model_load` 旗標 API 變動 |

---

## §1 問題現場

### 重構前的呼叫鏈

```
main.py
  └─ infer(image_list, image_dir, dcm_array, model_path)
       └─ paddleseglibs.predict.infer()
            ├─ parse_args()                ← 讀 sys.argv
            ├─ Config(args.cfg)
            ├─ cfg.model                   ← 建模型結構
            └─ paddleseg.core.predict.predict()
                 ├─ load_entire_model()    ← ⚠️ 載入權重
                 ├─ model.eval()
                 └─ for im_path in image_list:
                      └─ infer.inference(model, im, ...)
```

每次呼叫 `infer()`，**從 YAML 解析、模型結構建構、權重載入**全部重做一遍。

### 量化影響

從原 code log 訊息可看出：

```
Load model cost: 2.34s   ← 每次呼叫都會出現
predict img cost: 0.18s
```

假設 video 有 50 frames 要逐幀推論：

| 設計 | 總時間估算 |
|---|---|
| 每幀重 load | 50 × (2.34 + 0.18) ≈ **126 秒** |
| Model load 一次 | 2.34 + 50 × 0.18 ≈ **11.3 秒** |

**差距 11x**。對 video / 連續推論場景，這不是優化，是必要修正。

---

## §2 為什麼會這樣？背後的設計慣性

`paddleseglibs.predict.infer()` 原本是給「**CLI 一次性批次推論**」設計的。
作為命令列腳本，「跑完一批就結束」，所以 model load 寫死在函數內無妨。

但 `main.py` 把它**當成 library** import 呼叫時，
這個假設崩潰：library 函數理應可重複呼叫且廉價。

> **教訓**：寫 library function 時，要假設它會被頻繁呼叫。
> 凡是「呼叫時做的重活」都該想清楚是不是真的每次都該做。

---

## §3 解法光譜（從淺到深）

### Level 1 — Module-level global

```python
# paddleseglibs/predict.py
_MODEL = None

def infer(image_path, ...):
    global _MODEL
    if _MODEL is None:
        _MODEL = build_model_and_load_weights()
    return run_inference(_MODEL, image_path)
```

| 優點 | 缺點 |
|---|---|
| 改動最小 | 全域變數，難 mock、難測試 |
|  | 多模型場景失效（只能 cache 一個） |
|  | 換模型要重啟 Python（或加 reset 函數，醜） |

適合：玩具腳本、jupyter notebook 暫時湊用。
不適合：本專案（之後可能多模型並存）。

---

### Level 2 — Closure / Factory pattern

```python
def make_predictor():
    model = build_model_and_load_weights()  # 只執行一次
    def predict(image_path):
        return run_inference(model, image_path)
    return predict

# 使用
predict = make_predictor()
predict(image_path_1)
predict(image_path_2)
```

| 優點 | 缺點 |
|---|---|
| 沒有全域狀態 | 沒有 lifecycle 控制（無法顯式釋放） |
| 簡潔 | 沒有「狀態檢查」（model 已 load？） |
|  | 難擴充其他方法（例如 warmup、unload） |

適合：函式式風格、單純包裝。
不適合：未來會長出 `warmup()` / `release()` / `__enter__()` 的場景。

---

### Level 3 — Class with explicit lifecycle ★（本專案採用）

```python
class PaddleSegSegmenter(SegmenterBase):
    def __init__(self, config):       # 不做重活
        self._cfg = config
        self._predictor = None

    def load(self):                    # 顯式控制 setup
        if self._predictor is not None:
            return
        self._predictor = build_predictor(...)

    def predict(self, image_path, dcm_array=None):
        if self._predictor is None:
            self.load()                # auto-load fallback
        return predict_one(self._predictor, ...)
```

| 優點 | 缺點 |
|---|---|
| 狀態封裝、無全域污染 | 比 closure 多一些樣板 code |
| Lifecycle 清楚（init / load / predict / 未來 release） | 需要選好抽象介面（多想一點） |
| 容易測試（mock segmenter 物件） |  |
| 容易擴充（warmup, batch_predict, GPU 切換 ...） |  |
| 多 instance 並存（不同 config） |  |

適合：library 級的元件、之後會有多平台實作。

---

### Level 4 — Predictor pool / process pool

```python
class PredictorPool:
    def __init__(self, config, num_workers=4):
        self._workers = [spawn_worker(config) for _ in range(num_workers)]
    def predict(self, image_path):
        worker = self._next_idle_worker()
        return worker.run(image_path)
```

只有在以下情境才需要：
- 多 GPU 並行
- 多 process 跑同模型
- 高吞吐量 batch service

對研究型單機 pipeline：**過度設計**，本專案目前不採用。

---

## §4 為什麼本專案選 Level 3？

### 評估維度

| 維度 | Level 1 全域 | Level 2 closure | Level 3 class | Level 4 pool |
|---|---|---|---|---|
| 改動範圍 | 最小 | 小 | 中 | 大 |
| 測試友善度 | 差 | 中 | 好 | 中 |
| 多模型並存 | ❌ | ✅ | ✅ | ✅ |
| 擴充性（換平台） | 差 | 中 | **好** | 好 |
| 過度設計風險 | — | — | 低 | 高 |
| 跨 process 並行 | ❌ | ❌ | ❌ | ✅ |

### 決定因素

1. **`SegmenterBase` 抽象需求**：你明確要求「保留可換平台/模型接口」。
   ABC + 多型只有 class-based 設計能乾淨表達。

2. **可預期的擴充**：之後會加 `warmup()`、可能加 GPU memory 釋放。
   Class 有現成的位置可放，closure 要重寫整個結構。

3. **測試與 mock**：CLAUDE.md 強調醫療系統的可驗證性。
   `MockSegmenter(SegmenterBase)` 比 mock closure 容易。

4. **無犧牲**：Class 的樣板成本（`__init__` / `load` / `predict`）非常低，
   相對換來的擴充自由度 ROI 高。

---

## §5 程式碼結構對應

### 重構後的呼叫鏈

```
PaddleSegSegmenter(config)         ← 不做重活
  segmenter.load()                  ← 一次性 setup（含 load weights）
    build_predictor()
      Config(...)
      cfg.model
      load_entire_model()           ← ⚠️ 只在這裡發生，且只一次
  for frame in frames:
      segmenter.predict(...)        ← 共用 self._predictor
        predict_one()
          predict(skip_model_load=True)  ← 關鍵旗標
            # NOT load_entire_model
            model.eval()
            infer.inference(...)
```

### 關鍵旗標：`skip_model_load`

```python
# paddleseglibs/paddleseg/core/predict.py
if not skip_model_load:
    load_entire_model(model, model_path)
model.eval()
```

`skip_model_load=False`（預設）→ 舊行為，向後相容。
`skip_model_load=True` → 給 wrapper 用，假設 weights 已在 model 物件上。

> 這是 patch-first 的典範：**只加一個參數、預設值維持舊行為**，
> 沒人受影響、新呼叫者得到新能力。

---

## §6 常見陷阱與盲點

### 6.1 `model.eval()` 的位置

paddle / pytorch 的 `model.eval()` 切換模式（影響 dropout / batchnorm）。
這個動作是**冪等且 cheap**。

我們的決定：**留在 if 之外，每次 predict 前都呼叫**。
```python
if not skip_model_load:
    load_entire_model(model, model_path)
model.eval()   # ← 每次都呼叫，便宜且穩
```

為什麼？避免「曾經 `.train()` 過、忘了切回 eval」的狀態 bug。
即使理論上 model 在 load 後就一直是 eval，多花這一行不痛。

---

### 6.2 `paddle.set_device()` 該放哪？

放在 `build_predictor()` 內：device 是 setup 期決定的事。
如果放在 `predict_one()` 內，每次呼叫都重設，浪費且可能引發狀態混亂。

```python
def build_predictor(...):
    if device is None:
        device = auto_detect()
    paddle.set_device(device)        # ← 一次
    ...
```

---

### 6.3 GPU memory 在 Python 物件生命週期

`PaddleSegSegmenter` 物件持有 `self._predictor['model']`，這個 model 駐留在 GPU 顯存。

- 當 `segmenter` 變數離開 scope（或 `del segmenter`）→ Python GC 不保證立刻回收
- Paddle 的 GPU memory 也未必立刻釋放（pool 機制）

實務影響：
- 短命腳本：不需要管，程式結束 OS 自動清
- 長時程 service：可能需要顯式 `segmenter.release()` 機制（**TODO 留給未來**）

---

### 6.4 `parse_args()` 在 library 內的歷史包袱

舊 `infer()` 函數內呼叫 `parse_args()`，意味著：
- 它會讀 `sys.argv`
- 如果 main.py 自己也有 argparse，**會撞參數**
- 在 jupyter notebook 內呼叫會吃到 jupyter 的啟動參數

我們的處理：
- 保留 `parse_args()` 給舊 `infer()` shim 用（向後相容）
- 新介面 `build_predictor()` **完全不碰 sys.argv**
- 從 `PaddleSegSegmenterConfig` 注入所有參數，明確、可測試、無隱性 IO

> 「library 內的隱性 IO」是初學者很難察覺的反模式。
> 規則：**library function 不該讀環境變數、不該 parse argv、不該 print/log 之外的 IO**。

---

### 6.5 為什麼是 `load() + auto-fallback in predict()` 而不是 `__init__` 直接 load？

```python
# 我們選的（A）
def __init__(self, config):
    self._predictor = None         # 不做重活

def predict(self, ...):
    if self._predictor is None:
        self.load()                # 第一次自動 load
```

```python
# 拒絕的（B）
def __init__(self, config):
    self._predictor = build_predictor(...)  # 建構時就 load
```

| 維度 | (A) lazy load | (B) eager load |
|---|---|---|
| `__init__` 速度 | 快（毫秒級） | 慢（秒級） |
| 測試友善度 | 高（可建很多 instance 不負擔） | 低 |
| 控制流明確 | 高（要嘛顯式 load，要嘛第一次 predict 觸發） | 低（建構就有副作用） |
| 失敗時的鍋 | 在 `load()` 出，責任清楚 | 在 `__init__` 出，較難追 |

**Python 慣例**：`__init__` 不該做 IO / 重計算。
（同樣理由：requests `Session()` 不會立刻連線，sqlalchemy `engine()` 不會立刻打 DB）

---

## §7 進一步閱讀

- Python `abc` module（ABC base class 的標準寫法）
- "Effective Python" Item 19：functions vs. classes（何時該升級）
- "Clean Code" Ch. 6：Objects and Data Structures
- Paddle `paddle.set_device` / `paddle.no_grad` 文件
- `dataclasses` 標準函式庫（PaddleSegSegmenterConfig 的基礎）

---

## §8 本次重構 TL;DR

| Before | After |
|---|---|
| `infer()` 每次呼叫重 load 模型 | `PaddleSegSegmenter.load()` 一次性，`predict()` 共用 |
| 全域 `parse_args()` 污染 sys.argv | `PaddleSegSegmenterConfig` 顯式注入 |
| Model load 在演算法層內部 | Model load 在 wrapper（algorithm/segmentation/） |
| 強制存 PNG 副作用 | `save_predictions` 可控；config 預設關閉 |
| 換平台需改 paddleseglibs | 換平台只需新 `OnnxSegmenter(SegmenterBase)` 子類 |

---

## §9 變更紀錄

| 日期 | 版本 | 變更 | 動因 |
|---|---|---|---|
| 2026-05-24 | 0.1 | 補 SNAPSHOT 元資料表；H2 標題改 §N 編號；末段「未來介面變動請更新」備註刪除（已併入元資料「過期條件」） | 對齊 `CLAUDE.md` §10.2 雙軌規範 + `docs/STYLE.md` §2 |
