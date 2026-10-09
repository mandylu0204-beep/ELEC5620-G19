param([string]$PythonExecutable = 'python')
$ErrorActionPreference = 'Stop'
$appRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExecutable -m venv (Join-Path $appRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Use a working Python 3.11+ installation.' }
}
Push-Location (Join-Path $appRoot 'backend')
try {
    if (Test-Path -LiteralPath 'requirements.lock') {
        & $venvPython -m pip install --disable-pip-version-check -r requirements.lock
        if ($LASTEXITCODE -ne 0) { throw 'Locked Python dependency installation failed.' }
        & $venvPython -m pip install --disable-pip-version-check --no-deps -e .
    } else {
        & $venvPython -m pip install --disable-pip-version-check -e '.[dev]'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Backend installation failed.' }
} finally { Pop-Location }
Push-Location (Join-Path $appRoot 'frontend')
try {
    if (Test-Path -LiteralPath 'package-lock.json') { & npm.cmd ci } else { & npm.cmd install }
    if ($LASTEXITCODE -ne 0) { throw 'Frontend installation failed.' }
} finally { Pop-Location }
if (-not (Test-Path -LiteralPath (Join-Path $appRoot '.env'))) {
    Copy-Item -LiteralPath (Join-Path $appRoot '.env.example') -Destination (Join-Path $appRoot '.env')
}
Write-Host 'Setup complete. Run: .\scripts\start.ps1'
