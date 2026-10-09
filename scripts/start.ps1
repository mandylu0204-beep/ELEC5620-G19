param([int]$BackendPort = 8000, [int]$FrontendPort = 5173)
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) { throw 'Run .\scripts\setup.ps1 first.' }
& $venvPython (Join-Path $PSScriptRoot 'dev.py') --backend-port $BackendPort --frontend-port $FrontendPort
if ($LASTEXITCODE -ne 0) { throw 'Development services stopped with an error.' }
