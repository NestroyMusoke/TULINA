$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
& $python "$root\scripts\import_fixtures.py"
& $python "$root\scripts\verify_phase0.py"
