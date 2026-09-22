param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('read','dump','attributes99','attributes110','restore-abilities','max-badges','restore-badges',
        'roster-teams','roster-players','retention-summary','retention-auto','retention-purge')]
    [string]$Action,
    [ValidateSet('phase2a','all110-clean-badges')]
    [string]$Expected,
    [int]$RosterTeam,
    [int]$RosterPlayer,
    [switch]$DebugMode
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
$toolArgs = @((Join-Path $PSScriptRoot 'src\player_tool.py'), $Action)
if ($Expected) { $toolArgs += @('--expected', $Expected) }
if ($DebugMode) { $toolArgs += @('--debug') }
if ($Action -eq 'roster-players') {
    if ($PSBoundParameters.ContainsKey('RosterTeam')) { $toolArgs += @('--team', $RosterTeam) }
}
elseif ($PSBoundParameters.ContainsKey('RosterTeam') -and $PSBoundParameters.ContainsKey('RosterPlayer')) {
    $toolArgs += @('--roster', $RosterTeam, $RosterPlayer)
}
& $pythonExe -I -B @toolArgs
exit $LASTEXITCODE