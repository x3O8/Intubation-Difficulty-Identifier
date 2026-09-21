$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { py -3.12 -m venv (Join-Path $Root '.venv') }
& $Python -m pip install --disable-pip-version-check --timeout 300 -r (Join-Path $Root 'requirements.txt')
& $Python -c "from airway.db import initialize; initialize(); print('Local database initialized.')"
Write-Host 'Setup complete. The Face Landmarker model is intentionally not downloaded at runtime.'
Write-Host 'Place an approved official face_landmarker.task at models\face_landmarker.task and document its hash in models\manifest.json.'
