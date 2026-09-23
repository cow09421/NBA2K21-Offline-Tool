$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$zig = Join-Path $project 'tools\toolchains\zig-x86_64-windows-0.15.2\zig.exe'
$out = Join-Path $project 'build\speed_engine'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$env:ZIG_GLOBAL_CACHE_DIR = Join-Path $project 'build\zig-cache-global'
$env:ZIG_LOCAL_CACHE_DIR = Join-Path $project 'build\zig-cache-local'
New-Item -ItemType Directory -Force -Path $env:ZIG_GLOBAL_CACHE_DIR,$env:ZIG_LOCAL_CACHE_DIR | Out-Null
if (-not (Test-Path -LiteralPath $zig)) { throw 'Zig 0.15.2 not available in project toolchains' }
& $zig cc -O2 -target x86_64-windows-gnu -shared (Join-Path $PSScriptRoot 'speed_engine_dll.c') (Join-Path $PSScriptRoot 'virtual_clock.c') -o (Join-Path $out 'SpeedEngine64_v2.dll') -lwinmm
if ($LASTEXITCODE -ne 0) { throw 'SpeedEngine64_v2.dll build failed' }
& $zig cc -O2 -DSPEED_TELEMETRY_COUNTERS -target x86_64-windows-gnu -shared (Join-Path $PSScriptRoot 'speed_engine_dll.c') (Join-Path $PSScriptRoot 'virtual_clock.c') -o (Join-Path $out 'SpeedEngine64_debug.dll') -lwinmm
if ($LASTEXITCODE -ne 0) { throw 'SpeedEngine64_debug.dll build failed' }
& $zig cc -O2 -target x86_64-windows-gnu (Join-Path $PSScriptRoot 'virtual_clock.c') (Join-Path $project 'tests\speed_engine\clock_test.c') -o (Join-Path $out 'ClockTest.exe')
if ($LASTEXITCODE -ne 0) { throw 'ClockTest build failed' }
& $zig cc -O2 -target x86_64-windows-gnu (Join-Path $project 'tests\speed_engine\test_target.c') -o (Join-Path $out 'SpeedEngineTestTarget.exe') -lwinmm
if ($LASTEXITCODE -ne 0) { throw 'TestTarget build failed' }
& (Join-Path $out 'ClockTest.exe')
if ($LASTEXITCODE -ne 0) { throw 'ClockTest failed' }
$release = Join-Path $project 'release\speed_engine'
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item -LiteralPath (Join-Path $out 'SpeedEngine64_v2.dll') -Destination (Join-Path $release 'SpeedEngine64.dll') -Force
$manifest = [ordered]@{
    compiler = 'Zig 0.15.2 x86_64-windows-gnu'
    dll_sha256 = (Get-FileHash (Join-Path $release 'SpeedEngine64.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    dll_debug_sha256 = (Get-FileHash (Join-Path $out 'SpeedEngine64_debug.dll') -Algorithm SHA256).Hash.ToLowerInvariant()
    telemetry_counters_release = 'OFF'
    test_target_sha256 = (Get-FileHash (Join-Path $out 'SpeedEngineTestTarget.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    clock_test_sha256 = (Get-FileHash (Join-Path $out 'ClockTest.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $out 'build_manifest.json') -Encoding UTF8
[System.IO.File]::WriteAllText((Join-Path $out 'build_manifest.json'), (($manifest | ConvertTo-Json) + "`r`n"), (New-Object System.Text.UTF8Encoding $false))
Write-Output ($manifest | ConvertTo-Json)
