$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$pnpm = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
if (-not (Test-Path "$root\.env")) { Copy-Item "$root\.env.example" "$root\.env" }
& $python -m pip install -e "$root[dev]"
& $pnpm install --dir "$root\frontend"
& $python "$root\scripts\import_fixtures.py"
Write-Host "Tulina is ready. Run .\scripts\dev.ps1"

