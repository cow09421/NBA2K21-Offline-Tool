# Changelog

## 2026-09-23 — Fix missing memory_read runtime dependency after project slimming

**ROOT CAUSE**：專案精簡後，`src\mycareer_unlock.py` 與 `src\hidden_options.py` 由「從 src/ 目錄執行」
改為從專案根執行（`python -I -B src\...`）。`-I`（isolated mode）不會把 script 所在目錄加入
`sys.path`，而這兩個模組只將 `tools/vendor` 插入 `sys.path`，未包含 `src/` 本身 —
導致 `from memory_read import ...`（及 `from mycareer_unlock import ...`）回報
`ModuleNotFoundError: No module named 'memory_read'`。

`memory_read.py` 檔案本身一直存在於 `OfflineTool\src\`（3,780 bytes，API surface 完整：
`Reader` / `K` / `W` / `MEMORY_BASIC_INFORMATION`）— 這是 import 路徑問題，不是檔案遺失。

**FIX（最小修改）**：
- `src\mycareer_unlock.py`：於 `tools/vendor` 插入後補上 `sys.path.insert(0, str(ROOT / 'src'))`
- `src\hidden_options.py`：同上

不修改任何 patch 邏輯、不修改 game EXE、不擴張 API 範圍。

**驗證**：
- `python -I -B src\mycareer_unlock.py status`：PASS（ModuleNotFoundError 消失，正常輸出）
- `hidden_options.py` import：PASS
- Build（GUI rebuild + acceptance harness）：PASS
- 55 regression tests：PASS（0.120s，無退化）
- GUI launch/routing smoke（含 5 個 park-meta 按鈕）：PASS
- Curry / LeBron / KD / PARK META / Restore routing：不受影響
- Offline MyCAREER functional gate（遊戲內進 MC 驗證）：NOT YET TESTED
