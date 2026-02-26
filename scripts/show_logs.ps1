$log = Join-Path $env:LOCALAPPDATA "tts-reader\logs\app.log"
if (-not (Test-Path $log)) {
  Write-Output "Log not found: $log"
  exit 1
}

Get-Content -Path $log -Tail 200
