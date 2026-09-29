param([int]$Port = 8000, [string]$ListenAddress = "127.0.0.1")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$runtime = Join-Path $PSScriptRoot ".venv/Scripts/python.exe"
if (-not (Test-Path -LiteralPath $runtime)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the Python virtual environment." }
    & $runtime -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}
Write-Host "Neural-Draft: http://localhost:$Port"
& $runtime -m uvicorn app:app --host $ListenAddress --port $Port --ws-max-size 16384
