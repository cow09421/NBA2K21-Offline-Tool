# Build the NBA 2K21 Offline Player Tool GUI (C# WinForms / .NET Framework 4.0).
# Uses the csc.exe bundled with Windows; no extra runtime or SDK required.
param(
    [string]$OutName = "NBA2K21 Player Tool.exe",
    [string]$ReleaseName = "NBA2K21 Offline Tool.exe"
)
$ErrorActionPreference = 'Stop'
$gui  = $PSScriptRoot
# Project root = two levels up from src\gui (the dir containing Player-Tool.ps1).
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$csc  = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { throw "csc.exe not found: $csc" }

$src = @(
    (Join-Path $gui 'Program.cs'),
    (Join-Path $gui 'MainForm.cs'),
    (Join-Path $gui 'SimpleJson.cs')
)
$out = Join-Path $gui $OutName
$releaseOut = Join-Path $projectRoot $ReleaseName

$refs = @(
    'System.dll',
    'System.Core.dll',
    'System.Windows.Forms.dll',
    'System.Drawing.dll'
) | ForEach-Object { "/reference:$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\$_" }

$args = @('/nologo', '/target:winexe', "/out:$out", '/optimize+') + $refs + $src

Write-Host "Compiling: $out"
& $csc $args
if ($LASTEXITCODE -ne 0) { throw "Build failed with exit code $LASTEXITCODE" }

Copy-Item -LiteralPath $out -Destination $releaseOut -Force
Copy-Item -LiteralPath $out -Destination (Join-Path $projectRoot $OutName) -Force
Write-Host "Done. Output: $out"
Write-Host "Release copy: $releaseOut"