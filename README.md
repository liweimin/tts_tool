# TTS Reader (Windows)

Win10/Win11 桌面常驻工具。  
在任意应用里选中文本后按快捷键（默认 `Alt+Q`）即可朗读。
再次选中文本并触发快捷键时，会立即打断当前朗读并播放新文本。

## 下载 EXE（Release）

- 稳定版本从 GitHub Releases 下载：
  - `https://github.com/liweimin/tts_tool/releases`
- `v0.1.0` 推荐下载资产：`tts-reader-uia.exe`

## 支持范围

- 已按通用链路覆盖：Chrome/Edge、Word、PDF（可复制文本）、VSCode 等
- 取词策略：
  - 优先 `UI Automation`（若已安装 `uiautomation`）
  - 失败后自动退化到剪贴板复制链路（`WM_COPY` / `Ctrl+C` / `Ctrl+Insert`，并尽量恢复原剪贴板）

如需额外启用 UIA 取词能力：

```powershell
pip install uiautomation
```

## 快速启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src\main.py
```

首次运行会自动生成 `config.json`（也可参考 `config.example.json` 手动创建）。

## 配置项

`config.json` 示例：

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

- `hotkey`: 全局快捷键（默认 `alt+q`）
- `copy_delay_ms`: 复制兜底等待时长
- `copy_retry_count`: 复制链路重试次数（建议 2）
- `max_chars`: 单次朗读最大字符数
- `tts_rate`: 语速
- `tts_voice_contains`: 按关键词匹配语音（可留空）
- `skip_if_no_text`: `false` 时取词失败会语音提示“未获取到选中文本”

## 控制面板

- 托盘菜单新增 `Settings` 和 `Logs`
- `Settings` 可修改并即时生效
- 保存热键时会检查是否和系统/其他软件冲突，冲突会弹窗提示
- `Logs` 页可直接复制日志文本，便于反馈问题

## 打包 EXE

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name tts-reader src\main.py
```

产物在 `dist\tts-reader.exe`。

或直接执行：

```powershell
.\scripts\build_exe.ps1
```

打包内置 UI Automation 增强版（更适合 VSCode/浏览器等复杂控件）：

```powershell
.\scripts\build_exe_uia.ps1
```

产物在 `dist\tts-reader-uia.exe`。

如果你在 VSCode / Chrome 里偶发“按了热键没声音”，优先使用 `tts-reader-uia.exe`。

## 冒烟测试

```powershell
.\scripts\smoke_test.ps1
```

## 日志位置

运行 EXE 后，日志固定写入：

`%LOCALAPPDATA%\tts-reader\logs\app.log`

例如：

`C:\Users\<用户名>\AppData\Local\tts-reader\logs\app.log`

查看最近日志：

```powershell
.\scripts\show_logs.ps1
```

## 版本发布

- 当前版本：`v0.1.0`
- 仓库内置 GitHub Actions 发布流：推送 `v*` tag 后会自动构建并上传以下 Release 资产：
  - `tts-reader-uia.exe`
  - `SHA256SUMS.txt`

## 注意事项

- 某些高权限窗口（管理员权限）可能无法被普通权限进程读取选区。
- PDF 若是扫描图片不可复制文本，需要额外 OCR 才能完整支持。
- 若使用 `Alt+Q` 偶发取词失败，建议改成 `Ctrl+Alt+Q`。
- 在复杂网页（自定义前端控件）里，偶发会出现“未获取到选中文本”；当前已做 UIA + 剪贴板兜底与重试，若仍复现请在 `Logs` 页面复制日志反馈。
