> 本輪驗收註：下文早期STRONG「不可寫」與後段EXPERIMENTAL_SAFE為歷史先後。現行允許7組實驗欄位限定copy，只驗證傳輸/可逆，不升格動畫語義；以VERIFIED_OFFSETS與當前ledger為準。

# PARK_META_FIELD_MAP — 2K21 Current Gen PARK META（2026-09-23）

驗收標準：底層資料鏈（source record → ID → target field → write → readback → reload），MC UI 顯示名稱為最低可信（F），不可否決 A-E。

## VERIFIED 欄位（可寫）

| # | semantic_name | offset | width | encoding | MC before | source value | readback | confidence |
|---|---|---|---|---|---|---|---|---|
| 1 | Jump Shot（已裝備跳投） | player +0x18D..0x18F | 3 bytes | [id_a, id_b, flag] | [178, 94, 0] = 跳投48 | Curry=[94, 81, 1]；TIM DUNCAN=[100, 87, 1]；LeBron=[128, 115, 1]；KD=[102, 89, 1] | VERIFIED（write+readback+restore A-B-A 全通過） | VERIFIED |

- 證據：A-B-A UI probe（48→TIM DUNCAN→48）diff 乾淨（僅 5 bytes 變、LeBron/Curry 0 變、addresses 不變）；
  write [94,81,1] readback 一致；restore [178,94,0] readback 一致。
- 0x18F = flag：0（101/149 球員）= 預設、1（48/149）= 已選擇/自訂。
- 0x345..0x346 在 Jump Shot 改動時也變（0→0x2C80→0→0x1640 減半）= 衰減計數器（UI 快取），非動作欄位。

## STRONG CANDIDATE 欄位（值分佈支持為動畫，語義未逐欄驗證 — 不可寫）

| offset | width | 多球員分佈（149 人掃描） | 解讀 | 驗證方法 |
|---|---|---|---|---|
| +0x304 | u8 | 76(36)/134(28)/81(23)/112(14)/100(13)/77(7) — 6 常見值+長尾 | dribble move 候選（Pro 系 ID 空間；球星=稀有值 36/15/19；QQ=129 為 Big Man 唯一值） | A-B-A（被鎖）或動畫資料庫 record |
| +0x31A | u8 | 33(30)/32(27)/34(19)/1(16)/0(14)/2(8) — 32/33/34 連續 | 動作 ID 空間候選（Basic 系？） | 同上 |
| +0x290 | u8 | 48(10)/43(7)/46(6)/37(6)/41(6)/0(6) | 動作 ID 候選 | 同上 |
| +0x226 | u8 | 3(6)/4(6)/22(5)/23(5)/21(5) | 動作 ID 候選（小值空間） | 同上 |
| +0x348 | u8 | 0(40)/30(6)/27(5)/28(5)/29(4) | 動作/屬性候選 | 同上 |
| +0x356 | u8 | 68(16)/70(16)/66(13)/136(10)/144(6) | 動作候選 | 同上 |
| +0x350 | u8 | 0(123)/142(4)/139(4)/130(3) | 稀有欄位 | 同上 |
| +0x1CA/+0x1EA | u8 | 0(143)/114/45/84/71/104 各1 | 稀有（成對 copy；LeBron=105/Curry=104/KD=68） | 同上 |

## REJECTED / 排除（非動畫）

| offset | 證據 | 結論 |
|---|---|---|
| +0x324 | 149 人全不同（uniq=149） | unique ID/fingerprint |
| +0x242 | 141 人不同 | unique ID/count |
| +0x074 | 2 的冪次分佈（0/2/4/8/10/12） | bitmask/flag |
| +0x31E | 2 的冪次分佈（0/32/48/8/16/112） | bitmask/flag |
| +0x32E | 2 的冪次分佈（4(84)/8(27)/132） | bitmask/flag |
| +0x311 | 75-80 連續 6 值高頻；LeBron=99/Curry=95/KD=98/QQ=58 | 能力顯示值（25-99），非 dribble |
| +0x18C | 四方 0/12/9/5；未隨 Jump Shot 改動變 | 非 Jump Shot 欄位 |
| +0x0F0..0x0F7 | face ID ×4 重複 | 外觀 copy |
| +0x16C..0x177 | body/physics floats（各球員不同） | body 型相關 |
| +0x188..0x18B | u32 模組 RVA/ID 候選（奇偶混合） | 未解（非統一指標） |
| +0x220..0x224 | 高熵分佈（uniq 127/72/125） | 未解 |

## 名稱 → ID 映射狀態

- 動畫顯示名稱字串池：heap 0x7ff470f1xxxx-0x7ff470f2xxxx（SESSION ONLY；「罰球 54」「勾射2」「大個子」「職業2」「快速移動」「職業{0}」格式字串已定位）
- exe .rdata：0x2390000+ = 球員姓氏 sorted 表（"The Quick"/"Mr. Clutch" 在字串池）
- **per-record ID 映射（name → animation ID）**：未定位 — 記錄結構不在字串池旁（連續字串，無 {ptr,name}/{name,id} 結構）
- V2F.L.SEngine.exe：27 個 RVA 常數無動畫類 — V2F 無動畫功能（VERIFIED）
- MC 動作選項清單：被 progression 門檻鎖（runtime attributes 110 仍鎖；重進 MC 仍鎖）— A-B-A 僅 Jump Shot 可行

## PARK META PRESET（已交付 — donor-copy engine）

已交付四 preset（tools/park_meta.py + GUI 四按鈕，全流程 smoke test 通過）：

| Preset | 來源 | 欄位數 | 驗證 |
|---|---|---|---|
| 2K21 PARK META | profile JSON（jump_shot=Curry VERIFIED + 0x304/0x31A/0x290 EXPERIMENTAL） | 4 | VERIFIED |
| Curry 動作包 | Curry roster（fresh resolve） | 8（8/8 readback） | VERIFIED |
| LeBron 動作包 | LeBron roster | 8（8/8 readback） | VERIFIED |
| KD 動作包 | KD roster | 8（8/8 readback） | VERIFIED |

Donor-copy 欄位集（ANIM_FIELDS）：0x18D（Jump Shot VERIFIED）+ 0x304/0x31A/0x290/0x226/0x348/0x356/0x350（EXPERIMENTAL_SAFE — 值=roster 實際動作 ID，語義=donor 動作槽位未逐欄命名）。
全鏈驗證：original→Curry→LeBron→KD→PARK META→Restore→original match 全通過（Jump Shot 編碼 [94,81,1]/[128,115,1]/[102,89,1]/[178,94,0] 逐一切換正確）。

仍未納入（name→ID 映射未解）：Dribble Style Quick / Signature Size-Up Pro 2 / Size-Up Escape Pro 2 / Moving Crossover Pro 2（0x304 可能為此槽位，語義未驗證）/ Moving Behind the Back Pro 6 / Moving Spin Basic 1 / Moving Hesitation Pro 4 / Triple Threat Normal 4 / Layup Long Athlete / Dunks。

## SESSION ONLY（勿沿用）

- PID <PID>、module base 0x7ff70a830000（2026-09-22 15:09:17 session）
- Player VAs：QQ=0x7ff4791dacb8、LeBron=0x7ff4790b9538、Curry=0x7ff479108708、KD=0x7ff4790c9e28
- 動畫名稱表 heap：0x7ff470f10000+
- 全部 SESSION ONLY — 每次執行重新 resolve（player_tool.discover + roster_browser）
