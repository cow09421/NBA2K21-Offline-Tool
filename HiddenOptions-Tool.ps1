param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('hidden-options-status','enable-hidden-options','disable-hidden-options')]
    [string]$Action
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
$script = Join-Path $PSScriptRoot 'src\hidden_options.py'
$toolArgs = @()
switch ($Action) {
    'hidden-options-status' { $toolArgs = @('status') }
    'enable-hidden-options' { $toolArgs = @('enable') }
    'disable-hidden-options'{ $toolArgs = @('disable') }
}
& $pythonExe -I -B @($script) @toolArgs
exit $LASTEXITCODE