# NBA 2K21 Offline Tool

NBA 2K21（PC）離線 MyCAREER 修改工具：讀取目前 MyCAREER 球員、修改 attributes/badges、
一鍵套用 NBA 球星動作包（animation preset）與 2K21 PARK META，並提供 fail-closed 的
原始狀態備份 / 還原。

所有寫入只針對遊戲行程記憶體中的 runtime player struct；不修改遊戲檔案、不碰線上服務。

## 功能

**球員修改**
- 讀取目前 MC / roster 球員（roster browser）
- 全能力 99 / 全能力 110
- 全徽章 / 恢復原徽章
- 恢復原能力

**動作包（animation packages）**
- Curry 動作包（donor-copy：直接從 roster 中 Curry 讀取動畫欄位）
- LeBron 動作包
- KD 動作包
- 2K21 PARK META（profile-based preset）
- 恢復原始動作（永遠回到第一次套用前的 ORIGINAL baseline）

**安全機制**
- process identity guard（PID / exe path / SHA256 / module base 每次重新解析）
- bounded write（只寫已驗證欄位範圍）
- readback verification（寫入後立即讀回比對）
- rollback on exception（任何失敗自動還原）
- ORIGINAL baseline immutable（不可被覆寫為修改值）

## 使用方式

```
# GUI（預編譯版本在 release\，或自行 build）
release\NBA2K21 Offline Tool.exe

# 命令列
.\Player-Tool.ps1 -Action read
.\Player-Tool.ps1 -Action attributes110
.\Park-Meta-Tool.ps1 -Action apply -JumpShot park_meta
.\Park-Meta-Tool.ps1 -Action apply -JumpShot curry
.\Park-Meta-Tool.ps1 -Action restore
```

GUI 流程：先「讀取目前球員」建立 baseline → 再按任一動作按鈕。
第一次套用動作包時會自動建立 ORIGINAL baseline。

## Speed Engine（實驗性 process time multiplier）

GUI「遊戲時間控制」視窗提供 0.10x／0.25x／0.50x／0.75x／1.00x，
與 NBA2K21 原生「比賽速度」設定分開。
自製 x64 Speed Engine（IAT hook QPC／GTC64／GTC／timeGetTime）已在受控 TestTarget 全數通過；
**0.75x 已通過 NBA2K21 gameplay 人工驗收（明顯慢於 1.00x、快於 0.50x，
切回 1.00x 正常，操作／音訊無異常；其餘倍率的 gameplay 未逐一驗收）**。
Telemetry 只顯示各 clock ACTIVE／NOT USED，不顯示累積呼叫次數；
正式 release 預設關閉 per-call counter（另建 debug DLL 供診斷）。
依賴 `runtime\python`、`speed_engine\controller.py`、`release\speed_engine\SpeedEngine64.dll`；
重建見 `speed_engine\Build-SpeedEngine.ps1`。

Native NBA2K21 Game Speed runtime research was closed after repeated differential scans produced no reliable authoritative value.
Process Time Multiplier is a separate implemented feature.

## Build

```
powershell -ExecutionPolicy Bypass -File .\Build.ps1
```

- GUI：C# WinForms（.NET Framework 4.0），使用 Windows 內建 csc.exe 編譯，無需 SDK。
- 後端：Python 3（stdlib only + vendor 開源庫，見下）。

### Python runtime

`Player-Tool.ps1` 從 `runtime\python\python.exe`（project-relative）載入隨附 Python。

本 repository 不含 Python runtime。取得方式：

1. 下載 [Python embeddable package](https://www.python.org/downloads/windows/)（3.11+ 建議）
2. 解壓到 `runtime\python\`
3. 啟用 `python._pth` 中的 `import site`（如需 pip）

任何標準 Python 3 安裝也可用（自行修改 ps1 中的 pythonExe 路徑）。

### vendor 開源庫

`tools\vendor\` 包含第三方開源庫（clone 後直接可用）：

| 庫 | 授權 | 用途 |
|---|---|---|
| capstone | BSD-3 | x86-64 反組譯（靜態驗證） |
| pefile | MIT | PE 解析（section/RVA） |
| dnfile / dncil | MIT | .NET assembly 反組譯（參考工具分析） |

## 驗證狀態

### VERIFIED

- Curry / LeBron / KD 動作包 GUI routing（fresh donor resolve → MC 逐欄 write/readback）
- 2K21 PARK META routing（profile-based）
- Jump Shot slot（`player +0x18D..0x18F`，3 bytes `[id_a, id_b, flag]`）—
  A-B-A probe + write + readback + restore + 重現 + MC re-entry persistence + gameplay 實測
- bounded write / readback verification
- original animation restore（ORIGINAL baseline immutable）
- runtime address re-resolution（跨遊戲重啟需重新 resolve；結構性 STATIC VERIFIED）
- 獨立 build（不依賴研究樹）
- regression tests（55 tests）

### EXPERIMENTAL

- 尚未完全解碼語義的 animation candidate fields
  （`0x304 / 0x31A / 0x290 / 0x226 / 0x348 / 0x356 / 0x350`）—
  donor-copy 使用的是 roster 球員的實際動作 ID（遊戲中真實存在的值），
  寫入有 readback 驗證與 rollback，但各欄位對應的動作槽位語義尚未逐欄命名驗證。

### UNRESOLVED

- 完整 animation name → ID mapping（動畫選單顯示名稱與內部 ID 的對應表）
- dunk / layup slot mapping
- persistent save-file animation write（存檔為加密容器，runtime write 為 session 內持久）
- 五套 MAX MyPLAYER templates（已暫停的後續專案）

## 相容性 / 限制

- 工具以 game EXE 的 SHA256 + AOB signature fail-closed 驗證；
  遊戲更新後 signature 變更會拒絕執行（不猜測）。
- 目前驗證針對的 build：NBA 2K21 PC（Epic/Steam 通用版），
  EXE SHA256 `5dbd9408dff48f3d36f34748ae505aacb73a9935e9a9eafb7f345cb9c6325556`。
- MC 球員識別固定為 roster 中 Lakers 隊的目標球員；其他 career 未驗證。
- 「我的動畫」UI 顯示可能不即時刷新（offline 解鎖狀態下的已知行為）；
  gameplay 行為與 memory readback 為主要驗收依據。

## 參考依賴（optional / reference）

開發過程中使用第三方修改器 `V2F.L.SEngine.exe` 作為反逆向參考（本 repository 不包含該檔案）。
相關分析見 `docs\REFERENCE_V2F.md`。

## 文件

| 文件 | 內容 |
|---|---|
| `docs\FINAL_ACCEPTANCE.md` | 最終驗收（14 項） |
| `docs\CURRENT_STATE.md` | 目前狀態 |
| `docs\BUILD_AND_RUN.md` | 建置與執行 |
| `docs\PARK_META_FIELD_MAP.md` | 動畫欄位地圖（VERIFIED/EXPERIMENTAL/REJECTED） |
| `docs\PARK_META_profile.json` | PARK META profile |
| `docs\OPENCODE_EVIDENCE_LEDGER.md` | 證據清冊 |
| `docs\VERIFIED_OFFSETS.md` | 已驗證 offsets |
| `docs\RESTORE_AND_SAFETY.md` | 還原與安全 |
| `docs\PORTABILITY_AUDIT.json` | 可攜性稽核 |
| `docs\unit_tests.txt` / `BUILD_ACCEPTANCE.txt` | 測試 / build 驗收記錄 |

## 免責聲明

本工具僅供單機離線模式使用與學習研究。請勿用於任何線上模式。
使用本工具所產生的存檔風險由使用者自行承擔（工具內建備份/還原機制可降低風險）。
