# TTS Reader Handoff (Minimal, 2026-02-26)

## 1. 目标与当前行为
- Win10/Win11 常驻桌面工具：用户选中文本后按热键朗读。
- 默认热键：`Alt+Q`。
- 朗读中再次触发会打断当前播报，直接读新选中文本。
- 目标覆盖：Chrome/Edge、Word、PDF（可复制文本）、VSCode 等。

## 2. 已实现能力
- 全局热键监听 + 托盘常驻。
- 取词链路：
  - 优先 UI Automation（若安装 `uiautomation`）。
  - 失败兜底：`WM_COPY -> Ctrl+C -> Ctrl+Insert`，含重试与等待策略。
- 语音引擎：`pyttsx3 (SAPI)`，支持抢占式中断播报。
- 配置与日志面板：
  - 托盘菜单有 `Settings` / `Logs`。
  - 使用独立进程打开 Tk 控制面板（避免 Tk 线程崩溃）。
  - Settings 保存后主进程自动热加载配置（约 0.5s 轮询）。
  - 修改热键时有占用冲突检测提示。
  - Logs 支持刷新与一键复制全部文本。
- 日志固定路径：`%LOCALAPPDATA%\tts-reader\logs\app.log`。

## 3. 关键文件
- 主流程：
  - `src/tts_reader/app.py`
  - `src/tts_reader/selection.py`
  - `src/tts_reader/speaker.py`
  - `src/tts_reader/hotkey.py`
- 控制面板：
  - `src/tts_reader/control_panel.py`
  - `src/tts_reader/cli.py`（`--control-panel` 入口）
- 配置与日志：
  - `src/tts_reader/config.py`
  - `src/tts_reader/logging_setup.py`
  - `config.json`
- 打包脚本：
  - `scripts/build_exe.ps1`
  - `scripts/build_exe_uia.ps1`

## 4. 当前默认配置
```json
{
  "hotkey": "alt+q",
  "copy_delay_ms": 260,
  "copy_retry_count": 2,
  "max_chars": 4000,
  "tts_rate": 180,
  "tts_voice_contains": "",
  "skip_if_no_text": false
}
```

## 5. 已知问题与下一步优先级
- 偶发网页场景仍可能出现“未获取到选中文本”（与站点控件实现有关），但日志已记录 `method` 与 `capture_ms` 便于定位。
- 需要继续优化“触发到发声”延迟（部分场景仍可感知 1-2s）。
- 需在真实用户机上回归验证：
  - 托盘点 `Settings/Logs` 是否稳定拉起。
  - 设置保存后主进程是否稳定即时生效。
  - 热键冲突提示是否符合预期。

## 6. 最小验证命令
- 开发运行：`python src\main.py`
- 控制面板单独运行：
  - `python src\main.py --control-panel --tab settings --config-path config.json --log-path $env:LOCALAPPDATA\tts-reader\logs\app.log`
- 编译检查：`python -m compileall src`
- 冒烟测试：`.\scripts\smoke_test.ps1`
- 打包（推荐 UIA 增强版）：`.\scripts\build_exe_uia.ps1`
- 快速看日志：`.\scripts\show_logs.ps1`

## 7. 关键约束（避免回归）
- 不要把 Tk 窗口放到主程序线程/子线程里直接跑；保持“独立进程控制面板”模式。
- 若调取词速度，优先看：
  - `selection._build_wait_profiles`
  - `config.copy_delay_ms`
  - `config.copy_retry_count`
