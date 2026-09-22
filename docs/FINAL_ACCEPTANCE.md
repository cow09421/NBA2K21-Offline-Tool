# FINAL ACCEPTANCE — 2026-09-23

|驗收項目|結果|證據／限制|
|---|---|---|
|1 GUI build|PASS|新位置Windows csc build成功；compiled GUI建立/Show/隱藏測試成功|
|2 Curry routing|PASS — RUNTIME VERIFIED|GUI→apply curry→fresh Warriors/Curry Stephen→MC，8/8|
|3 LeBron routing|PASS — RUNTIME VERIFIED|GUI→apply lebron→fresh Lakers/James LeBron→MC，8/8|
|4 KD routing|PASS — RUNTIME VERIFIED|GUI→apply kd→fresh Nets/Durant Kevin→MC，8/8|
|5 PARK META routing|PASS — RUNTIME VERIFIED|GUI→apply park_meta→profile JSON，4/4；不是donor|
|6 Restore original semantics|PASS — RUNTIME VERIFIED|immutable最初original；連續套用後8/8，full0x4E8 original match；重套用後恢復且baseline hash不變|
|7 animation write/readback|PASS（白名單值層級）|8-field donor與4-field profile；並非宣稱7個experimental語義已解碼|
|8 non-animation invariance|PASS（已知範圍）|每步0x4E8所有非目標bytes不變、名冊membership一致；外部未知progression未驗證|
|9 session address re-resolve|PASS|每操作新process/build/MC/donor解析；跨遊戲重啟STATIC VERIFIED，本輪未重啟|
|10 精簡版獨立build|PASS|Build.ps1 -Test；55 tests通過；無舊build輸入|
|11 仍依賴舊46GB研究樹|NO|isolated bundled Python、project-relative profiles/source/data；仍需Windows/.NET及指定game EXE|
|12 精簡版大小|見下方最終統計|包含參考EXE、Python、source zip及小型save backups|
|13 舊樹最大研究dump清理候選|見下方統計|REVIEW FIRST，只列未刪；不含未知大型save備份|
|14 最終位置|OfflineTool / ProjectArchive|同層原V2F.L.SEngine.exe hash不變|

## VERIFIED
本輪compiled GUI路由與啟動、donor8/PARK4傳輸讀回、原始恢復及重套用、既知struct範圍不變、55回歸測試、獨立build。Jump Shot編碼與既有Curry gameplay證據保持VERIFIED，本輪不新增gameplay。

## EXPERIMENTAL
0x304/0x31A/0x290/0x226/0x348/0x356/0x350仍EXPERIMENTAL_SAFE；本輪只驗bounded copy/readback/reversibility，不用人類名稱不明判FAIL，也不把raw readback升格為語義VERIFIED。

## UNRESOLVED
其餘PARK not_included名稱映射、dunk/layup slots、五MAX模板、template/save authoritative source、動畫save persistence、任意MC身份辨識與未知外部progression。当前目標固定q q/Lakers；不同身份fail closed。不做新研究或要求UI。

## 證據
RUNTIME_ACCEPTANCE.json、REAPPLY_ACCEPTANCE.json、park-meta-*.txt、BUILD_ACCEPTANCE.txt、unit_tests.txt、PORTABILITY_AUDIT.json、ORIGINAL_TREE_CHECK.json。
完整交易在../OfflineTool/data/park_sessions，每筆prepared/before/after/result。baseline與legacy來源一併保留。模擬test輸出的RUNTIME_VERIFIED只屬fixture，不作live證據；live以RUNTIME_ACCEPTANCE為準。
原46GB樹所有1012檔仍存在且大小不變（不是50GB全文hash聲明），原始參考EXE前後SHA一致。沒有修改game EXE，沒有重做逆向或要求使用者操作。

## 最終統計
保存版約 **68.9 MiB**（含參考EXE）；OfflineTool約 **44.1 MiB**。
舊樹 **46.82 GiB**；大型研究dump候選 **31.74 GiB**，仍需使用者REVIEW FIRST。
