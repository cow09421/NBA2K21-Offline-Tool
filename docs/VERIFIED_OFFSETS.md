# 已知欄位與分級
Build SHA256：5dbd9408dff48f3d36f34748ae505aacb73a9935e9a9eafb7f345cb9c6325556。未知build fail closed，不硬編碼PID/base/heap。

|欄位|位置|等級|
|---|---|---|
|姓/名|+0x00/+0x28，各40B UTF16|既有VERIFIED|
|Face ID|+0x6C u16|既有VERIFIED|
|能力|+0x41B，56B；raw//3+25，99=222，110=255|既有VERIFIED；本輪regression及非污染比對|
|徽章|+0x4B7，37B；layout JSON固定模板|既有VERIFIED；本輪regression及非污染比對|
|Jump Shot|+0x18D..18F，3B|VERIFIED：original[178,94,0]、Curry[94,81,1]、LeBron[128,115,1]、KD[102,89,1]|
|其餘donor欄位|0x304/31A/290/226/348/356/350，各1B|EXPERIMENTAL_SAFE，只驗bounded傳輸可逆，語義未知|
|名冊|team stride0x1058；name+0x2B4；17個8B slots|既有VERIFIED，每次解析|
|0x345..346|衰減counter|非動畫，不寫|
|0x324..327|身份指紋bytes|一致性guard，不是全球唯一save ID|

0x6129220不是已找到template caps；12×56已否定，雙區容量14×24靜態已知，owner未知。見evidence/GPT6_P1_READER_REPORT.md。preview/editor/static tables/save source不可混淆。
