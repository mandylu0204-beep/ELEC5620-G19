$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
Push-Location (Join-Path $appRoot 'backend')
try {
    & $venvPython -m pytest --basetemp (Join-Path $appRoot 'var\pytest-temp')
    if ($LASTEXITCODE -ne 0) { throw 'Backend checks failed.' }
    & $venvPython -m app.export_contracts --check
    if ($LASTEXITCODE -ne 0) { throw 'Exported schema is out of date.' }
} finally { Pop-Location }
Push-Location (Join-Path $appRoot 'frontend')
try {
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
