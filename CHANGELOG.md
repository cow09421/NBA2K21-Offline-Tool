# Changelog

## 2026-09-24 — 0.75x preset, telemetry streamline, research cleanup

- GUI 倍率新增 0.75x（共 0.10x／0.25x／0.50x／0.75x／1.00x）；engine 本就接受任意 0.05–2.0 倍率，未改核心。
- Telemetry 視窗改顯示 QPC／GTC64／GTC／timeGetTime ACTIVE／NOT USED，不再顯示累積呼叫次數；
  正式 release 預設關閉 per-call counter（compile-time `SPEED_TELEMETRY_COUNTERS`，另建 debug DLL 供診斷，
  以 `last_virtual_qpc` 變化驗證 hook 命中）。
- TestTarget 驗證 1.00→0.75→0.50→0.75→1.00 比率正確、monotonic、switch continuity、IPC seq==ack、
  restore 1.00x、disconnect restore、reconnect 後 0.75x；55 regression＋GUI presets=5 gating PASS。
- Native NBA2K21 Game Speed runtime research was closed after repeated differential scans produced no reliable authoritative value.
- Process Time Multiplier is a separate implemented feature.
- 研究廢料（memory scans、candidate JSON、screenshots、GearNT zip、舊 logs/dumps）已 MOVE 到本地屎山，未進 repo。
- 0.75x 的 NBA2K21 gameplay 尚未人工驗收；正式 release DLL 的 counter-OFF swap 待遊戲工作階段結束後執行。

## 2026-09-23 — Fix missing memory_read runtime dependency after project slimming

**ROOT CAUSE**：專案精簡後，`src\mycareer_unlock.py` 與 `src\hidden_options.py` 由「從 src/ 目錄執行」
改為從專案根執行（`python -I -B src\...`）。`-I`（isolated mode）不會把 script 所在目錄加入
`sys.path`，而這些模組只將 `tools/vendor` 插入 `sys.path`，未包含 `src/` 本身 —
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

## 2026-09-23 — Fix sibling-import regression in player_tool.py; MC identity = Roxy Migurdia

**IMPORT FIX**：`src\player_tool.py` 的 8 個 sibling imports（`locator` / `memory_read` /
`clean_baseline` / `session_baseline` / `phase2a` / `sessions` / `retention` / `roster_browser`）
在 `python -I` 模式下全部無法解析（同 memory_read regression 的根因）。修法一致：
imports 前補 `sys.path.insert(0, str(Path(__file__).resolve().parent))`。
locator 演算法未修改。

**MC IDENTITY FIX**：MC 目標身份由硬編碼 `q q` 改為固定 identity
**First Name = Roxy / Last Name = Migurdia**（`tools\park_meta.py`）：

- `find_mc()`：Roxy Migurdia 優先；legacy q q 玩家僅作為一次性 migration source
  （找不到 Roxy 且 legacy 無歧義時才接受；其餘情況 fail closed）
- identity guard 保留全部既有檢查：player struct / team / slot / Face ID / membership /
  name_bytes / unique_id_bytes / game_sha256 — 姓名是 guard 的一部分
- `migrate_name()`：一次性 Q Q → Roxy Migurdia，只寫兩個 40-byte UTF-16 姓名 buffer，
  readback 驗證 + 非 name bytes 不變檢查，然後顯式 rebind ORIGINAL baseline 的 identity key
  （fields/checksum 不動）
- 已驗證：migration PASS → identity PASS（跨 process 重啟後仍 Roxy Migurdia）→
  animation apply/restore routing PASS → status 回 ORIGINAL
- 附帶修正：`find_player` 名字匹配改為 given-first（與 `ReadRosterPlayer.report['name']`
  的 First + Last 格式一致），同時接受兩種順序以保持對稱姓名相容

**GUI**：新增按鈕「設定 MC 姓名：Roxy Migurdia」（`park-meta-migrate-name`）；
`Park-Meta-Tool.ps1` 新增 `migrate-name` action。

**驗證**：
- player_tool.py import：PASS（`roster-teams` 正常執行）
- Current player / roster read：PASS（identity = Roxy Migurdia，Lakers slot 14）
- Migration：PASS（readback First=Roxy / Last=Migurdia，非 name bytes 不變）
- 跨 process 重啟：identity PASS（q q 不再需要）
- Animation routing（apply park_meta → RUNTIME_VERIFIED → restore → RUNTIME_VERIFIED →
  status ORIGINAL）：PASS
- 55 tests：PASS（0.117s，無退化）
- GUI build + smoke（6 個 park-meta 按鈕）：PASS

## 2026-09-23 — Speed Engine 實驗版（未完成遊戲驗收）

- 新增自製 x64 IAT 時鐘攔截 POC、連續虛擬 clock、倍率與失聯恢復控制、只允許指定遊戲/測試程序的 controller。
- 新增 1.00x／0.50x／0.25x／0.10x GUI 預設與 telemetry 狀態視窗；未 READY 前按鈕停用。
- TestTarget 的四種 clock 倍率、還原、IPC、thread access、失聯恢復、重新連線與錯誤目標拒絕通過。
- NBA2K21 只完成主選單舊版1.00x QPC telemetry。其 QUIT ack 未確認；新版尚未在全新遊戲工作階段驗證，MyCAREER gameplay 效果未驗證。
- 既有 63 項 Python 測試與 GUI 啟動檢查通過。GearNT 僅作靜態研究，沒有加入產品。
