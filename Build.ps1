param([switch]$Test)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'build') | Out-Null
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=Join-Path $PSScriptRoot 'build'
$env:TMP=$env:TEMP
& (Join-Path $PSScriptRoot 'src\gui\build.ps1')
$csc="$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$acceptSource=Join-Path $PSScriptRoot 'tests\GuiAcceptance.cs'
$acceptOut=Join-Path $PSScriptRoot 'build\GuiAcceptance.exe'
& $csc /nologo /target:exe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll "/out:$acceptOut" $acceptSource
if($LASTEXITCODE -ne 0){throw 'GUI acceptance harness build failed'}
if($Test){
 & (Join-Path $PSScriptRoot 'runtime\python\python.exe') -B -m unittest discover -s (Join-Path $PSScriptRoot 'tests') -v
 if($LASTEXITCODE -ne 0){throw 'Tests failed'}
 & $acceptOut
 if($LASTEXITCODE -ne 0){throw 'GUI launch/routing smoke failed'}
}
