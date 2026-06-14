$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -m venv .venv
}

.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
pyinstaller --noconfirm IndustrialMqttTagSimulator.spec
Write-Host "Build complete: dist\IndustrialDualProtocolTagSimulator\IndustrialDualProtocolTagSimulator.exe"
