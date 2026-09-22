param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('apply','restore','backup','status')]
    [string]$Action,
    [ValidateSet('park_meta','curry','lebron','kd','original')]
    [string]$JumpShot = 'park_meta'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:TEMP = Join-Path $PSScriptRoot 'build'
$env:TMP = $env:TEMP
$pythonExe = Join-Path $PSScriptRoot 'runtime\python\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw '缺少隨附 Python runtime' }
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'build') | Out-Null
$toolArgs = @((Join-Path $PSScriptRoot 'tools\park_meta.py'), "--$Action")
if ($Action -eq 'apply') {
    # JumpShot is the profile name (park_meta) or donor name (curry/lebron/kd).
    if ($JumpShot -eq 'original') { $toolArgs = @((Join-Path $PSScriptRoot 'tools\park_meta.py'), '--restore') } else { $toolArgs += @($JumpShot) }
}
& $pythonExe -I -B @toolArgs
exit $LASTEXITCODE
