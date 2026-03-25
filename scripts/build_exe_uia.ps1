$ErrorActionPreference = "Stop"

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python venv not found. Create it first: python -m venv .venv"
}

# Avoid file lock failures during rebuild.
Get-Process | Where-Object { $_.ProcessName -eq "tts-reader-uia" } | Stop-Process -Force -ErrorAction SilentlyContinue

& $python -m pip install pyinstaller uiautomation
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install build dependencies."
}

& $python -m PyInstaller `
  --clean `
  --noconfirm `
  tts-reader-uia.spec

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller UIA build failed."
}

Write-Output "Build completed: dist\\tts-reader-uia.exe"
