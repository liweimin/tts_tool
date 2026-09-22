# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

## [0.6.1] - 2026-09-22

### Fixed
- **中英文混合文本（夹杂中文句子）翻译支持**：
  - 优化文本语言检测算法：重构判定规则，只要文本中包含实质性连贯英文内容（如英文从句或词组），即使开头、中间或结尾夹杂有一两句中文说明（如邮件署名、提示语等），也能准确判定并进入翻译链路。
  - 修复源语言自动检测陷阱：当文本中包含中文时，Google 翻译请求中将源语言明确指定为 `en`，避免 Google 因识别出前缀中文而误判整篇为 `zh-CN` 导致原样输出英文的问题；自动实现“翻译英文句子、完好保留中文字句”。
  - 纯中文文本保持 0 延迟秒读：纯中文句子或仅含有孤立术语（如 `用 Python 遇到了一个 Bug`）依然走本地/快速通道直接发声，不产生多余网络开销。

## [0.6.0] - 2026-09-17

### Added
- **Edge-TTS 神经网络语音支持**：接入微软 Edge 神经网络超自然语音合成，默认启用“微软晓晓”（`zh-CN-XiaoxiaoNeural`），彻底告别传统机械音；同时提供云希（阳光解说男声）、云健（影视解说男声）、晓伊（抒情女声）、方言以及高品质美式英语等丰富音色。
- **SAPI5 离线无缝降级**：具备网络容灾机制，若无网络或在线服务短暂不可用，自动平滑切换至本地 Windows SAPI5 语音引擎发声，保障基础可用性。
- **开机自动启动**：新增开机自启选项（注册于 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`），默认随系统静默常驻托盘，支持在设置面板中一键开启/关闭。
- **高清晰度专属图标与任务栏标识**：设计并嵌入了高分辨率专属发音波形图标（包含 256x256、128x128、64x64、48x48、32x32、16x16 多尺寸），托盘与设置窗口均换上全新视觉，并通过 `SetCurrentProcessExplicitAppUserModelID` 确保在 Windows 任务栏中正确聚合与高精度呈现。

### Changed
- **控制面板体验升级**：
  - 语音设置卡片新增“语音引擎”选项（Edge 神经网络 / Windows 系统语音）。
  - 新增“Edge 声音风格”下拉选单，清晰标注各声音的名字与特色（如温柔亲切、阳光活泼等），方便用户快速直观切换。
  - 新增“开机自动启动”复选框。
  - 系统托盘菜单全面汉化，支持双击托盘图标快捷打开控制面板。

### Fixed
- **中文截图 OCR 逐字停顿朗读问题**：针对 Windows 原生 OCR 识别中文汉字时在每字间硬编码插入空格导致 TTS 变成“逐字蹦字”朗读的现象，增加智能汉字与标点去空格及折行自然拼接算法，恢复行云流水般的流畅朗读。
- **英文截图 OCR 翻译稳定性提升**：翻译服务采用更具容错性的 POST 链路，并追加 MyMemory 双通道备选容灾；优化语言检测容差，消除 OCR 零星杂字符引起的英文误识别与漏翻。

## [0.5.1] - 2026-04-02

### Fixed
- Fixed screenshot selection cropping on Windows systems with display scaling enabled by mapping overlay coordinates to the captured image's physical pixel space.
- Enabled DPI awareness at process startup so screenshot save/OCR coordinates stay aligned more reliably across scaled displays.

## [0.5.0] - 2026-03-25

### Added
- Added a dedicated screenshot save flow with default hotkey `Alt+E`.
- Added config field `save_screenshot_hotkey` for customizing the screenshot save hotkey.
- Added config field `screenshot_save_dir` for customizing where captured PNG files are stored.
- Saving a screenshot now writes the absolute file path to the clipboard for easy sharing.

### Changed
- The screenshot save feature now defaults to the Desktop folder and is configurable in the settings panel.
- The settings panel now exposes screenshot save hotkey and save directory controls.
- The UIA EXE build script now uses the lightweight `.spec` path again, avoiding accidental bundling of deprecated OCR dependencies.

### Fixed
- Fixed a regression in the screenshot OCR flow where `capture_ms` could raise `NameError` and break screenshot reading.
- Fixed screenshot cancellation handling by aligning the overlay result states across the app.

## [0.4.0] - 2026-03-02

### Added
- **Auto Translation**: Added a lightweight, key-less network translation mechanism to automatically translate selected English text (or OCR results) to Chinese before reading it aloud.
- Added language detection filter to bypass translation for purely Chinese text selections naturally, preserving zero latency.
- Added a new configuration toggle `enable_auto_translation` which is exposed on the settings panel.

### Changed
- Increased the default height of the UI control panel window so that settings at the bottom are not obscured.

## [0.3.7] - 2026-02-27

### Changed
- **Packaging Stability**: Reverted overly aggressive Python standard library exclusions that were causing PyInstaller `zipfile`/`urllib` hook missing module exceptions at startup.
- **Packaging**: Applied safe PyInstaller excludes (abandoned `numpy`) and deployed UPX binary compression. The single executable size plummeted from the initial ~100MB to an ultimate ~16MB.

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
