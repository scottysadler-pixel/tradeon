# TRADEON launcher script
# Usage: just double-click this file, or run `.\RUN.ps1` in PowerShell.

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

if (-not (Test-Path "$projectRoot\.venv\Scripts\streamlit.exe")) {
    Write-Host "Setting up virtual environment for the first time..." -ForegroundColor Yellow
    py -3.14 -m venv "$projectRoot\.venv"
    & "$projectRoot\.venv\Scripts\python.exe" -m pip install --upgrade pip
    & "$projectRoot\.venv\Scripts\python.exe" -m pip install -r "$projectRoot\requirements.txt"
}

Write-Host "Launching TRADEON at http://localhost:8501 ..." -ForegroundColor Green
& "$projectRoot\.venv\Scripts\streamlit.exe" run "$projectRoot\app.py"
