$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$pnpm = "C:\Users\X1 Yoga\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
& $python -m pytest "$root\backend\tests" -q
& $pnpm --dir "$root\frontend" test
& $pnpm --dir "$root\frontend" build

