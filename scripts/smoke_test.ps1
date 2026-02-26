$ErrorActionPreference = "Stop"

$python = ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  throw "Python venv not found. Create it first: python -m venv .venv"
}

$env:PYTHONPATH = "src"

@'
import threading
import time

from tts_reader.app import ReaderApp
from tts_reader.config import AppConfig

status = {"error": None}

def _run():
    try:
        app.start()
    except Exception as exc:
        status["error"] = repr(exc)

app = ReaderApp(AppConfig(hotkey="ctrl+shift+f12", screenshot_hotkey="ctrl+shift+f11"))
thread = threading.Thread(target=_run, daemon=True)
thread.start()
time.sleep(3)
app.request_stop()
thread.join(timeout=6)
if status["error"] is not None:
    print("SMOKE_FAIL", status["error"])
elif thread.is_alive():
    print("SMOKE_FAIL thread_alive")
else:
    print("SMOKE_OK")
'@ | & $python -
