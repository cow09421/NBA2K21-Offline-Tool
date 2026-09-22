# Read-only snapshot; writes logs/dumps only under this project.
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path $projectRoot 'build'
$env:TMP = $env:TEMP
$pythonExe = Join-Path $PSScriptRoot 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw '缺少隨附 Python runtime' }
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'build') | Out-Null
if (-not (Test-Path -LiteralPath $pythonExe)) { throw '找不到 Python 執行環境，請調整 Read-SelectedPlayer.ps1 中的 pythonExe。' }
& $pythonExe -I -B (Join-Path $projectRoot 'src\locator.py') @args
if ($LASTEXITCODE -ne 0) { throw '唯讀定位未通過驗證。詳細原因請查看 logs。' }
