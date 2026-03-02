# TTS Reader Handoff (Minimal, v0.4.0)

## 1. 当前产品能力
- Win10/Win11 常驻工具，选中文本后按 `Alt+Q` 朗读。
- 截图 OCR 朗读：`Alt+R`，截图结果保留在系统剪贴板。
- **(NEW)** 英译中能力：支持智能拦截检测，选中或截图英文内容，将自动进行免 Key 网络翻译为中文然后朗读。
- 新请求会抢占旧请求：
  - 文本/截图互相抢占。
  - 旧截图请求会被中止，只执行最新请求。

## 2. 当前架构
- `ReaderApp` 主调度：`src/tts_reader/app.py`
- 文本取词链路：`src/tts_reader/selection.py`
- 截图 OCR 链路：`src/tts_reader/screen_ocr.py`
- 智能网络翻译引擎：`src/tts_reader/translator.py`
- 语音播放与中断：`src/tts_reader/speaker.py`
- 全局热键监听：`src/tts_reader/hotkey.py`
- 控制面板（独立进程）：`src/tts_reader/control_panel.py`

## 3. 关键配置（默认）
```json
{
  "hotkey": "alt+q",
  "screenshot_hotkey": "alt+r",
  "copy_delay_ms": 260,
  "copy_retry_count": 2,
  "max_chars": 4000,
  "tts_rate": 180,
  "tts_voice_contains": "",
  "skip_if_no_text": false,
  "enable_auto_translation": true
}
```

## 4. 日志与发布
- 日志路径：`%LOCALAPPDATA%\tts-reader\logs\app.log`
- 日志滚动：仅保留 `app.log` 和 `app.log.1`
- Release 构建：`.github/workflows/release.yml`
- 本地打包：`scripts/build_exe_uia.ps1`

## 5. 下次迭代优先点
- 继续优化截图 OCR 到发声延迟（复杂截图仍有体感延迟）。
- 增加 OCR 参数可配置（速度/精度模式切换）。

## 6. 最小回归命令
- `python -m compileall src`
- `.\scripts\smoke_test.ps1`
- `.\scripts\build_exe_uia.ps1`
