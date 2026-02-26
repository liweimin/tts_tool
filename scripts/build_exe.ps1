$ErrorActionPreference = "Stop"

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python venv not found. Create it first: python -m venv .venv"
}

# Avoid file lock failures during rebuild.
Get-Process | Where-Object { $_.ProcessName -eq "tts-reader" } | Stop-Process -Force -ErrorAction SilentlyContinue

& $python -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install pyinstaller."
}

& $python -m PyInstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --name tts-reader `
  src\main.py

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller build failed."
}

Write-Output "Build completed: dist\\tts-reader.exe"
