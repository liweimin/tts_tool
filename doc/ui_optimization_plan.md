# TTS Reader 控制面板 UI 升级方案

当前 `control_panel.py` 使用的是 Python 内置的 `tkinter` 和默认的 `ttk` 样式。此原生样式在现代 Windows 系统下显得非常陈旧。

为了让界面符合现代审美（Windows 11 Fluent Design），同时考虑到这是一个轻量级常驻工具，不能因为换个 UI 就让打包后的 `exe` 体积暴增。以下提供三套可落地的改造方案，开发人员可直接参考执行。

---

## 方案 A：引入 `sv_ttk` 主题库（推荐，极低成本）

**特点**：**无需重构代码**，只需增加两行代码，即可让原本丑陋的 ttk 控件直接变身为 Windows 11 原生风格（支持深/浅色模式自适应）。Exe 体积几乎没有影响。

1. **依赖安装**：
   ```powershell
   pip install sv-ttk
   ```
2. **代码修改** (`src/tts_reader/control_panel.py`)：
   ```python
   # 在文件顶部引入
   import sv_ttk
   
   def run_control_panel(config_path: Path, log_path: Path, tab: str = "settings") -> int:
       root = tk.Tk()
       root.title("TTS Reader 设置")
       # 加上圆角和现代阴影处理 (可选，仅Win11有效)
       # root.wm_attributes("-transparentcolor", ...)
       
       # ... 原有代码 ...
       
       # 在 root.mainloop() 之前调用，一键应用 Windows 11 风格
       sv_ttk.set_theme("dark") # 或者 "light"，推荐跟随系统自动切换
       root.mainloop()
   ```

---

## 方案 B：使用 `CustomTkinter` 重构（推荐，现代化程度高）

**特点**：用 `CustomTkinter` 替换原生的 `tk` / `ttk`。控件变更为 `CTkButton`, `CTkEntry` 等。这能带来真正的圆角控件、护眼深色模式和更现代的字体渲染。

1. **依赖安装**：
   ```powershell
   pip install customtkinter
   ```
2. **重构要点**：
   - 将 `tk.Tk()` 替换为 `customtkinter.CTk()`
   - 将所有的 `ttk.Label`、`ttk.Entry`、`ttk.Button` 替换为 `customtkinter.CTkLabel` 等。
   - **排版优化调整**：
     - 去除原先密集排布的网格（Grid），采用卡片式（Card）布局。将“热键设置”、“识别参数”、“语音参数”用 `CTkFrame` 作为卡片背景分隔开来。
     - 将原本生硬的“Save & Apply”按钮换成带主色调的圆角大按钮 `CTkButton(fg_color="#0067c0")`。

---

## 方案 C：使用 `PyQt6` + `qfluentwidgets`（重构成本高，极致原生体验）

**特点**：直接使用完整的 Fluent Design 体系，拥有系统级原生动画、亚克力半透明背景。缺点是打包体积会增加几十MB。
1. **重构要点**：完全废弃 Tkinter，采用 PySide6 / PyQt6 开发。适合后续如果需要开发独立主界面的情况，对于一个目前的轻量级“单页设置面板”来说，**偏重**。

---

## 具体的排版与交互细节优化（需同步修改）

无论采用上述哪种技术栈，现有的界面在“视觉排版”上都应做以下优化，请研发在改动时同步调整：

1. **视觉分组（卡片化）**：
   - 目前所有参数都堆在一个大 Tab 里。需要用边框或背景色将设置项分为三大块：
     - **【快捷键设置】**（文本朗读热键、截图识别热键）
     - **【剪贴板与 OCR】**（重试次数、延迟缓冲）
     - **【语音引擎】**（语速、音色、空文本跳过提示）
2. **文案易读性优化**：
   - 原文案 `"Text Hotkey"` -> 建议改为 `"选中文本朗读快捷键 (Text Hotkey)"`
   - 原文案 `"Voice Contains"` -> 建议改为 `"指定发音人 (包含关键词，如 Huihui)"`
3. **增加底部固定栏**：
   - 将 `Reload` 和 `Save & Apply` 按钮及状态提示语，从长列表的底部，移到一个**永远固定在窗口最底部**的独立 Frame 中，右对齐。这样用户不需要滚动就能随时保存。
4. **日志面板优化**：
   - 给 Log 文件路径增加一个可点击的“直接打开所在文件夹”的文本链接按钮。
   - 文本框默认改为黑底绿字或黑底白字，提升极客感和可读性。
