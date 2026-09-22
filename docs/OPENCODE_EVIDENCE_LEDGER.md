# 當前Evidence Ledger — 2026-09-23
|Finding|等級|證據|限制|
|---|---|---|---|
|GUI五按鈕到backend|RUNTIME VERIFIED|park-meta-*.txt/RUNTIME_ACCEPTANCE.json|compiled RunProcess，不看MC UI名稱|
|Donor8欄/PARK4欄|RUNTIME VERIFIED|data/park_sessions prepared/result|傳輸可逆≠所有欄位語義|
|original恢復/重套用|RUNTIME VERIFIED|RUNTIME_ACCEPTANCE/REAPPLY_ACCEPTANCE.json|0x4E8完全相同，baseline hash未改|
|非目標不變|RUNTIME VERIFIED|before/after/result|0x4E8及membership，外部未知progression不聲稱|
|Jump Shot|VERIFIED|本輪readback，既有Curry gameplay|未新增gameplay|
|其他7個donor欄位|EXPERIMENTAL_SAFE|bounded copy/readback/restore|未命名，不升格語義|
|未納入的dribble/layup/dunk映射|UNRESOLVED|profile not_included|不研究|
|每次resolve|RUNTIME VERIFIED；跨重啟STATIC VERIFIED|各journal與source|未實際重啟|
|獨立build/啟動|VERIFIED|BUILD_ACCEPTANCE/PORTABILITY_AUDIT|Windows/.NET及指定game必要|

下列是歷史模板研究，不是当前任務，不表示五模板完成。

# OpenCode Evidence Ledger

分類VERIFIED必須看限定範圍；靜態指令不等於runtime、UI真值不等於memory欄位。WEAK未知項不是正向證據。

|Finding|Evidence|Confidence|Status|Source file / snapshot / tool|可作writer依據|
|---|---|---|---|---|---|
|A/B body五欄與hydration lifecycle|歷史hydration快照及GPT6 ledger|高|VERIFIED|GPT6_SESSION_INDEX.md；hydration_20260922_052916|否：只讀body/schema|
|A/B variant排序不同|歷史body對照|高|VERIFIED|GPT6_HANDOFF_2026-09-22.md §B|否：反而禁止固定struct|
|雙區24-byte stride、容量14列|row*24指令，兩區delta0x150|高／靜態|VERIFIED|analysis/template_sessions/p1_5bfb231bb156466ea7a19bace9b9a425/four_readers.txt|否：UI caps未連通|
|12×56 caps假設|被實際index否定|高|REJECTED|analysis/template_sessions/p1_5bfb231bb156466ea7a19bace9b9a425/four_readers.txt|否／禁止|
|F(b)及range公式|讀取與clamp機器碼|高／靜態非runtime hit|VERIFIED|analysis/template_sessions/p1_5bfb231bb156466ea7a19bace9b9a425/helpers_callers.txt|否|
|body調整低高界用途|helper body參數與插值；UI未逐欄匹配|中高|STRONG|GPT6_P1_READER_REPORT.md|否|
|0x6129220即已找到template caps|缺row/UI身份，B仍A|不足|REJECTED|本主交接K/H|否|
|loader memcpy不是serializer|後兩個指定refs與IAT|高／靜態|VERIFIED|analysis/template_sessions/p1_5bfb231bb156466ea7a19bace9b9a425/exact_callers.txt|否|
|A test60/99與editor完整UI|圖片及逐欄JSON|高／UI限定|VERIFIED|analysis/template_sessions/cap_probe_c0b5bd275db540ddb0276c82556a9b98；analysis/template_sessions/cap_probe_a759b9c5a1884346b0a9fa39590757df；analysis/template_sessions/cap_probe_8091a236ba2a46d382f4c34ed241a0ba|否|
|個別能力99|只有overall99，無個別99|高／圖片限定|REJECTED|analysis/template_sessions/cap_probe_a759b9c5a1884346b0a9fa39590757df/A_test_overall99.png|否|
|94→93→94可逆|近距離投籃與剩餘0→1→0|高／UI限定|VERIFIED|analysis/template_sessions/cap_probe_8091a236ba2a46d382f4c34ed241a0ba；analysis/template_sessions/cap_probe_e5bde5bb786948f7b3900d5ea2de31bc|否：缺authoritative delta|
|64B/672B在94→93不變|hash comparison|高／有限範圍|VERIFIED|analysis/template_sessions/cap_probe_e5bde5bb786948f7b3900d5ea2de31bc/A_allocation_close93.json|否|
|24float讀取及插值caller|root+13DF4列步進4，range插值|高／靜態|VERIFIED|analysis/template_sessions/p1_5bfb231bb156466ea7a19bace9b9a425/allocation_caller_followup.txt|否|
|24float分配比例|A形狀一致|中高|STRONG|analysis/template_sessions/cap_probe_e5bde5bb786948f7b3900d5ea2de31bc/restored_input24.json|否|
|具體cache/seed用途|編輯不變、B不跟隨，確切context未知|低|WEAK|analysis/template_sessions/cap_probe_27e58d56562041758abdadd703b8b510/input24.json|否|
|global鏈為當前editor owner|B UI不同但body與ratio仍A|高／反證|REJECTED|analysis/template_sessions/cap_probe_27e58d56562041758abdadd703b8b510|否／禁止|
|B editor真值已取得|19項與physicals/badge點数|高／UI；名稱依操作脈絡|VERIFIED|analysis/template_sessions/cap_probe_27e58d56562041758abdadd703b8b510/B_allocation_ui.json|否|
|B row0|body identity不匹配，不能歸屬|不足|REJECTED|analysis/template_sessions/cap_probe_27e58d56562041758abdadd703b8b510/report.json|否|
|authoritative owner/serializer/persistence|尚未定位或測試|無|WEAK|OPENCODE_WRITE_READINESS.md|否|
|MC Jump Shot primary field +0x18D..0x18F|A-B-A UI probe（48→TIM DUNCAN→48）diff 乾淨：僅5 bytes變、LeBron/Curry 0變、addresses不變；write [94,81,1] readback一致；restore [178,94,0] readback一致|高／runtime|VERIFIED|analysis/fast_mc_max/anim_baseline、anim_changed_timduncan、anim_restored_48、anim_poc_write_curry.py、tools/park_meta.py|是：唯一已驗證動畫欄位|
|Curry Jump Shot編碼 [94,81,1]|roster ground truth（Curry struct）+ A-B-A + write/readback/restore|高|VERIFIED|analysis/fast_mc_max/PARK_META_FIELD_MAP.md|是|
|LeBron [128,115,1]／KD [102,89,1] Jump Shot編碼|roster struct同schema值|高／同schema|STRONG（語義同Jump Shot欄位）|anim_baseline四方位元組|是（同欄位寫入路徑）|
|0x18F flag（0=預設/1=已選擇）|149人掃描：0(101)/1(48)；A-B-A中0→1|高|VERIFIED|park_multi_scan.py|N/A|
|0x304=動畫欄位候選|149人分佈：76(36)/134(28)/81(23)/112(14)/100(13) — 6常見值+長尾|中高|STRONG（語義未逐欄驗證）|park_multi_scan.py|否：先驗證|
|0x324/0x242=unique ID非動畫|149/141人全不同|高|REJECTED|park_multi_scan.py|否|
|0x074/0x31E/0x32E=bitmask|2的冪次分佈|高|REJECTED（非動畫ID）|park_multi_scan.py|否|
|0x311=能力顯示值非dribble|75-80連續6值高頻；LeBron=99/Curry=95/KD=98/QQ=58|高|REJECTED（非動畫）|park_multi_scan.py|否|
|MC動作選項清單被progression門檻鎖|罰球/轉身跳投/勾射僅1選項；runtime attributes=110仍鎖；重進MC仍鎖|高／UI+runtime|VERIFIED|使用者截圖+park_check_attrs.py|N/A|
|V2F.L.SEngine無動畫功能|27個RVA常數（建模/主宰/防守類）無動畫類；MoveWind=WPF視窗拖曳|高|VERIFIED|v2f_full_il.txt、anim_inventory.txt|N/A|
|動畫名稱字串池（heap）|0x7ff470f1xxxx-0x7ff470f2xxxx：罰球54/勾射2/大個子/職業2/快速移動/職業{0}格式字串|高／SESSION ONLY|VERIFIED|park_anim_table.py、anim_names_localized.txt|N/A：無per-record ID映射|
|name→ID映射未定位|名稱表=連續字串無{ptr,name}結構；V2F無動畫常數；動作清單被鎖|高|WEAK（邊界明確）|park_record_struct.py、park_list_struct.py|否|
|Curry Jump Shot經離開MC重進後保留|write [94,81,1]→使用者離開MC重進→status仍[94,81,1]|中高／runtime in-session|STRONG（in-session persistence）|park_meta.py --status輸出|部分：in-session持久化|
|PARK META工具鏈可用|backup/apply/restore/status全fail-closed；apply→restore→apply重現性通過|高|VERIFIED|tools/park_meta.py、Park-Meta-Tool.ps1、GUI整合build成功|是|
|Jump Shot gameplay生效|使用者練習場確認：write [94,81,1] 後實際投籃動作=Curry|高／gameplay E級|VERIFIED（完整驗證鏈：A-B-A→write→readback→restore→重現→in-session→gameplay）|使用者實測 2026-09-23|是：RUNTIME ANIMATION EDITING 方法論成立|
|PARK META profile engine|profile JSON（jump_shot VERIFIED + 0x304/0x31A/0x290 EXPERIMENTAL_SAFE）；apply 內建自動 ORIGINAL baseline；readback+rollback per field|高|VERIFIED|tools/park_meta.py、PARK_META_profile.json|是|
|Donor-copy animation fields|8 fields（0x18D Jump Shot VERIFIED + 0x304/0x31A/0x290/0x226/0x348/0x356/0x350 EXPERIMENTAL_SAFE）；donor 每次 fresh resolve（Curry/LeBron/KD）；值=roster 實際動作 ID（合法）|高|VERIFIED（寫入+readback+rollback 路徑）／EXPERIMENTAL（0x304 等語義=donor 動作槽位未逐欄命名）|tools/park_meta.py apply_donor|是（bounded field-level copy，禁止整段 memcpy）|
|四 preset 熱切換|original→Curry 8/8→LeBron 8/8→KD 8/8→PARK META 4/4→Restore 2/2→original match；Jump Shot 編碼逐一切換正確（[94,81,1]/[128,115,1]/[102,89,1]/[178,94,0]）|高／自動驗證|VERIFIED|park_sessions/20260923_05*、GUI smoke test|是|
|GUI 四按鈕整合|[套用 2K21 PARK META][Curry 動作包][LeBron 動作包][KD 動作包][恢復原動作]；Park-Meta-Tool.ps1 dispatch；build 成功；全流程 smoke test 通過|高|VERIFIED|src/gui/MainForm.cs、Park-Meta-Tool.ps1、NBA2K21 Offline Tool.exe|是|
