# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.3.2] - 2026-02-27

### Changed
- **Packaging**: Applied aggressive PyInstaller excludes (abandoned dozens of unused Python stdlibs) and deployed UPX binary compression. The single executable size plummeted from the initial ~100MB to an ultimate ~12.5MB.

## [0.3.0] - 2026-02-27

### Added
- Added a custom Tkinter transparent full-screen overlay for instant mouse-drag area selection.
- Added a subtle "ding" notification sound immediately upon screen capture release.

### Changed
- **Major**: Replaced `rapidocr-onnxruntime` with native `Windows.Media.Ocr` API via `winrt`. OCR is now instantaneously executed directly by the OS.
- **Major**: Executable packaging size was drastically reduced from ~60MB-100MB to ~20MB by stripping heavy ML model dependencies.
- Screen capturing entirely bypasses the system clipboard now, resolving previous data pollution and improving privacy and performance.

## [0.2.1] - 2026-02-27

### Changed
- Modernized the control panel UI with the `sv_ttk` Fluent Design dark theme.
- Grouped settings into logically separated cards with localized Chinese labels.
- Fixed UI layout to ensure action buttons are always visible at the bottom.

## [0.2.0] - 2026-02-26

### Added
- Screenshot OCR reading flow with default hotkey `Alt+R`.
- Tray shortcut `Screenshot OCR`.
- Config field `screenshot_hotkey` with conflict validation.
- Request preemption for screenshot OCR: stale screenshot requests are aborted when a newer request arrives.

### Changed
- Settings UI now supports independent text and screenshot hotkeys.
- Build/release scripts now bundle `rapidocr-onnxruntime` for screenshot OCR.
- Hotkey callback dispatch is now asynchronous to avoid blocking subsequent triggers.
- Speech interruption logic was hardened to reliably stop current playback before new playback.
- Logging policy now keeps only recent logs (`app.log` and `app.log.1`).

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
