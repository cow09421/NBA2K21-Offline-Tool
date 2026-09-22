# Restore / Safety
原始來源：OfflineTool/data/park_sessions/original.json，只在首次建立，apply/手動backup不覆蓋；8組白名單、identity、checksum不符拒絕。legacy_original.json保留來源但僅抽白名單，不回寫整段。
每次核對build/process、MC唯一q q/Lakers、名冊slot、身份指紋；donor隊名全名重新解析。寫前重查membership，只寫committed writable non-executable data。prepared落盤後才寫。失敗返回非零並rollback已触及白名單；身份變了就禁止亂寫rollback，記錄錯誤。
整個0x4E8 exact expected diff；非目標漂移即FAIL，不忽略counter來灌PASS；因此動態比賽中可能保守拒絕。
本session最後restore通過，遊戲維持original動作；能力/徽章、EXE及save未修改。
