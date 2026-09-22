# Build / Run
1. Windows x64，內建.NET Framework v4 csc及Windows PowerShell。runtime/python含Python3.12標準庫，tools/vendor含pefile/capstone，不需舊tree、網路、pip、Codex cache。
2. 在OfflineTool執行：powershell -NoProfile -ExecutionPolicy Bypass -File .\Build.ps1 -Test
3. 產出根目錄NBA2K21 Offline Tool.exe與NBA2K21 Player Tool.exe；src/gui副本相同。build/GuiAcceptance.exe為驗收harness。
4. 開NBA2K21 Offline Tool.exe。遊戲仍須位於E:\SteamLibrary\NBA2K21\NBA2K21.exe並符合SHA；此為game依賴，非舊研究樹依賴。
5. 遊戲若以管理員執行，工具須同等權限。無遊戲或identity不符拒絕。

CLI：Park-Meta-Tool.ps1 -Action apply -JumpShot curry/lebron/kd；PARK用park_meta；恢復-Action restore；status只讀。
logs/dumps/analysis全在新位置。動畫baseline/journals在data/park_sessions；必須備份original.json，不能用當前preset替代。
55項unit tests為mock/offline；GuiAcceptance無參數只建UI驗tag。tests/runtime_acceptance.py會真實寫動畫，僅明確opt-in，build不自動執行它。
舊baseline遷移已在同session完成。新save或身份不符拒絕，不靠刪baseline繞過。每次重新resolve地址；本輪未重啟遊戲。

## 第三方與支援檔
runtime/python/LICENSE.txt保留Python license；pefile/capstone保留套件既有授權註記。debug/tracing支援source僅為舊mock regression依賴，非本輪研究入口。
