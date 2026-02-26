# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] - 2026-02-26

### Added
- Global hotkey reading flow with default `Alt+Q`.
- System tray app with `Read Again`, `Settings`, `Logs`, and `Exit`.
- Settings UI for hotkey, copy/timing, TTS rate/voice, and no-text behavior.
- Hotkey conflict detection in Settings (warns when occupied by system/other apps).
- Logs UI with refresh and one-click copy.
- Build scripts for normal and UIA-enhanced EXE.

### Changed
- Text capture pipeline now prefers UI Automation and falls back to clipboard chain (`WM_COPY`, `Ctrl+C`, `Ctrl+Insert`) with retries.
- Speech engine supports preemption: a new hotkey request interrupts current playback.
- Config updates are hot-reloaded by the running app.

### Known Issues
- Some complex web pages may still occasionally return no selected text due to control implementation details.
- A small capture delay can occur in fallback paths when first attempt misses.
