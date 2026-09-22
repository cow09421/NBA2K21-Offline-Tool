# 當前狀態 — 2026-09-23
本檔取代舊handoff執行優先順序；停止研究，完成驗收、修正、精簡副本及獨立build。

## 修正（只在OfflineTool副本）
1. GUI球星由錯誤-Action curry/lebron/kd改成-Action apply -JumpShot對應donor；PARK維持apply預設profile，Restore維持restore。
2. 球星/Restore納入GUI結果處理；動畫按鈕採獨立後端baseline驗證，不受能力baseline未載入阻擋。
3. Restore取消0x74+2及0x180+480整段回寫，限定8組10 bytes白名單；不再覆蓋0x345..346等counter。
4. 整筆交易先持久化before/prepared，逐欄寫、全0x4E8 readback/invariance；失敗回滾所有已觸及欄位（含partial write），返回非零；跨行程鎖防並行。
5. ORIGINAL immutable schema2綁build/name/face/membership/name bytes/0x324..327身份指紋，checksum核對，不沿用VA；手動backup不覆蓋original。
6. 舊baseline僅同歷史process/base/VA且8欄全部符合original時遷移，保存舊hash與來源；沒有把Curry當original。
7. x64 resolver補HANDLE argtypes/restype；分別關閉讀寫handle，修復舊handle覆蓋洩漏。
8. dispatch改隨附Python -I -B；profile/data/journal走新位置相對路徑，不讀舊analysis。
9. MC apply_patch只補無original規格時的明確RuntimeError拒絕，有效patch行為不改；55項離線regression通過。

## 實測
歷史PID<PID>、creation UTC2026-09-22 15:09:17，SESSION ONLY。q q/Lakers/Face1/slot14重新解析。
Compiled GUI實例啟動，按鈕tag/label/gating核對，實際RunProcess→PowerShell→Python。
original→Curry8欄→LeBron8欄→KD8欄→PARK4欄→Restore8欄全部成功，最後0x4E8整塊完全相同。再Curry→Restore成功，original hash不變。
PARK只覆寫宣告4欄，不清除前一donor另外4欄，這是profile行為。

## 限制
MC目前固定q q/Lakers，不是任意career辨識；未解碼save ID。身份不符拒絕。0x324指紋不聲稱跨存檔全球唯一。
非目標驗證涵蓋0x4E8及名冊membership，包括此範圍內name/face/body/position/attributes/badges/counters；不聲稱外部pointer或未知全存檔progression也驗證。
未重啟遊戲或新增gameplay/UI/持久化測試；每次重新resolve有runtime證據，跨重啟路徑僅STATIC VERIFIED。
