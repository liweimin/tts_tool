$ErrorActionPreference = "Stop"

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python venv not found. Create it first: python -m venv .venv"
}

# Avoid file lock failures during rebuild.
Get-Process | Where-Object { $_.ProcessName -eq "tts-reader-uia" } | Stop-Process -Force -ErrorAction SilentlyContinue

& $python -m pip install pyinstaller uiautomation rapidocr-onnxruntime
if ($LASTEXITCODE -ne 0) {
  throw "Failed to install build dependencies."
}

$uiaBin = ".venv\Lib\site-packages\uiautomation\bin"
$uiaX64 = Join-Path $uiaBin "UIAutomationClient_VC140_X64.dll"
$uiaX86 = Join-Path $uiaBin "UIAutomationClient_VC140_X86.dll"
if (-not (Test-Path $uiaX64) -or -not (Test-Path $uiaX86)) {
  throw "UI Automation DLLs not found in $uiaBin"
}

& $python -m PyInstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --name tts-reader-uia `
  --hidden-import uiautomation `
  --collect-all uiautomation `
  --collect-all rapidocr_onnxruntime `
  --add-binary "$uiaX64;uiautomation\bin" `
  --add-binary "$uiaX86;uiautomation\bin" `
  src\main.py

if ($LASTEXITCODE -ne 0) {
  throw "PyInstaller UIA build failed."
}

Write-Output "Build completed: dist\\tts-reader-uia.exe"
