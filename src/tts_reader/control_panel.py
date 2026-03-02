from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from typing import Callable
import subprocess

import sv_ttk

from .config import AppConfig, read_config, write_config, parse_hotkey, validate_config
from .hotkey import is_hotkey_available


def run_control_panel(config_path: Path, log_path: Path, tab: str = "settings") -> int:
    initial_tab = "logs" if tab == "logs" else "settings"

    root = tk.Tk()
    root.title("TTS Reader 控制面板")
    root.geometry("820x660")
    root.minsize(760, 580)

    # Apply modern theme
    try:
        sv_ttk.set_theme("dark")
    except Exception:
        pass

    style = ttk.Style(root)
    # Adjust style if needed; sv_ttk handles most things automatically
    style.configure("Status.TLabel", foreground="#4caf50") # Use a green tint for success

    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 0))

    settings_tab = ttk.Frame(notebook)
    logs_tab = ttk.Frame(notebook)
    notebook.add(settings_tab, text="系统设置")
    notebook.add(logs_tab, text="运行日志")

    hotkey_var = tk.StringVar(root)
    screenshot_hotkey_var = tk.StringVar(root)
    copy_delay_var = tk.StringVar(root)
    copy_retry_var = tk.StringVar(root)
    max_chars_var = tk.StringVar(root)
    tts_rate_var = tk.StringVar(root)
    tts_voice_var = tk.StringVar(root)
    skip_empty_var = tk.BooleanVar(root)
    enable_translation_var = tk.BooleanVar(root)
    status_var = tk.StringVar(root)

    log_path_var = tk.StringVar(root, str(log_path))
    logs_text: tk.Text | None = None

    def set_status(message: str, is_error: bool = False) -> None:
        if is_error:
            style.configure("Status.TLabel", foreground="#e53935")
        else:
            style.configure("Status.TLabel", foreground="#4caf50")
        status_var.set(("[错误] " if is_error else "") + message)

    def load_config_to_form() -> None:
        config = read_config(config_path)
        hotkey_var.set(config.hotkey)
        screenshot_hotkey_var.set(config.screenshot_hotkey)
        copy_delay_var.set(str(config.copy_delay_ms))
        copy_retry_var.set(str(config.copy_retry_count))
        max_chars_var.set(str(config.max_chars))
        tts_rate_var.set(str(config.tts_rate))
        tts_voice_var.set(config.tts_voice_contains)
        skip_empty_var.set(config.skip_if_no_text)
        enable_translation_var.set(config.enable_auto_translation)
        set_status("已加载当前配置。")

    def parse_int(raw: str, field: str, minimum: int, maximum: int | None = None) -> int:
        try:
            value = int(raw.strip())
        except Exception as exc:
            raise ValueError(f"【{field}】必须是整数。") from exc
        if value < minimum:
            raise ValueError(f"【{field}】不能小于 {minimum}。")
        if maximum is not None and value > maximum:
            raise ValueError(f"【{field}】不能大于 {maximum}。")
        return value

    def collect_config_from_form() -> AppConfig:
        hotkey = hotkey_var.get().strip().lower()
        screenshot_hotkey = screenshot_hotkey_var.get().strip().lower()
        if not hotkey:
            raise ValueError("文本朗读快捷键不能为空。")
        if not screenshot_hotkey:
            raise ValueError("截图朗读快捷键不能为空。")
        parse_hotkey(hotkey)
        parse_hotkey(screenshot_hotkey)

        copy_delay_ms = parse_int(copy_delay_var.get(), "配置延迟缓冲", minimum=80)
        copy_retry_count = parse_int(copy_retry_var.get(), "复制备用重试次数", minimum=1, maximum=6)
        max_chars = parse_int(max_chars_var.get(), "单次最大朗读字符数", minimum=10)
        tts_rate = parse_int(tts_rate_var.get(), "语速", minimum=60, maximum=400)

        config = AppConfig(
            hotkey=hotkey,
            screenshot_hotkey=screenshot_hotkey,
            copy_delay_ms=copy_delay_ms,
            copy_retry_count=copy_retry_count,
            max_chars=max_chars,
            tts_rate=tts_rate,
            tts_voice_contains=tts_voice_var.get().strip(),
            skip_if_no_text=bool(skip_empty_var.get()),
            enable_auto_translation=bool(enable_translation_var.get()),
        )
        validate_config(config)
        return config

    def on_apply() -> None:
        try:
            config = collect_config_from_form()
        except ValueError as exc:
            messagebox.showerror("配置验证失败", str(exc))
            return

        current = read_config(config_path)
        if _has_hotkey_conflict(
            current=current,
            new_config=config,
        ):
            messagebox.showwarning(
                "热键冲突",
                "快捷键已被系统或其它软件占用，请换一个组合。",
            )
            set_status("检测到热键冲突，配置未保存。", is_error=True)
            return

        write_config(config, config_path)
        set_status("配置已保存，主程序会自动生效。")
        messagebox.showinfo("保存成功", "配置已保存并通知主程序自动生效。")
        load_config_to_form()

    def refresh_logs() -> None:
        if logs_text is None:
            return
        log_path_var.set(str(log_path))
        logs_text.delete("1.0", tk.END)
        logs_text.insert(tk.END, read_log_tail(log_path))
        logs_text.see(tk.END)

    def copy_logs() -> None:
        if logs_text is None:
            return
        text = logs_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showinfo("提示", "当前没有需要复制的日志。")
            return
        root.clipboard_clear()
        root.clipboard_append(text)
        messagebox.showinfo("复制成功", "日志文本已复制到剪贴板。")

    def open_log_dir() -> None:
        if log_path.exists():
            subprocess.Popen(f'explorer /select,"{log_path}"')
        else:
            messagebox.showinfo("提示", "文件暂不存在。")

    _build_settings_tab(
        settings_tab=settings_tab,
        hotkey_var=hotkey_var,
        screenshot_hotkey_var=screenshot_hotkey_var,
        copy_delay_var=copy_delay_var,
        copy_retry_var=copy_retry_var,
        max_chars_var=max_chars_var,
        tts_rate_var=tts_rate_var,
        tts_voice_var=tts_voice_var,
        skip_empty_var=skip_empty_var,
        enable_translation_var=enable_translation_var,
    )
    logs_text = _build_logs_tab(
        logs_tab=logs_tab,
        log_path_var=log_path_var,
        on_refresh=refresh_logs,
        on_copy=copy_logs,
        on_open_dir=open_log_dir,
    )

    # 底部固定操作栏
    bottom_bar = ttk.Frame(root, padding=10)
    bottom_bar.pack(fill=tk.X, side=tk.BOTTOM)
    
    status = ttk.Label(bottom_bar, textvariable=status_var, style="Status.TLabel")
    status.pack(side=tk.LEFT, padx=(5, 0))

    ttk.Button(bottom_bar, text="保存并生效", command=on_apply, style="Accent.TButton").pack(side=tk.RIGHT, padx=5)
    ttk.Button(bottom_bar, text="重新加载", command=load_config_to_form).pack(side=tk.RIGHT, padx=5)

    load_config_to_form()
    if initial_tab == "logs":
        refresh_logs()
        notebook.select(logs_tab)
    root.mainloop()
    return 0


def _build_settings_tab(
    settings_tab: ttk.Frame,
    hotkey_var: tk.StringVar,
    screenshot_hotkey_var: tk.StringVar,
    copy_delay_var: tk.StringVar,
    copy_retry_var: tk.StringVar,
    max_chars_var: tk.StringVar,
    tts_rate_var: tk.StringVar,
    tts_voice_var: tk.StringVar,
    skip_empty_var: tk.BooleanVar,
    enable_translation_var: tk.BooleanVar,
) -> None:
    # 包装容器支持网格滚动或单纯的流式布局
    container = ttk.Frame(settings_tab, padding=14)
    container.pack(fill=tk.BOTH, expand=True)

    # === 【热键配置】 ===
    hotkey_frame = ttk.LabelFrame(container, text="快捷键设置", padding=14)
    hotkey_frame.pack(fill=tk.X, pady=(0, 15))
    hotkey_frame.columnconfigure(1, weight=1)

    _add_labeled_entry(hotkey_frame, 0, "选中文本朗读快捷键", hotkey_var)
    _add_labeled_entry(hotkey_frame, 1, "截图朗读快捷键", screenshot_hotkey_var)

    # === 【剪贴板与 OCR】 ===
    ocr_frame = ttk.LabelFrame(container, text="容错与延时管理", padding=14)
    ocr_frame.pack(fill=tk.X, pady=(0, 15))
    ocr_frame.columnconfigure(1, weight=1)

    _add_labeled_entry(ocr_frame, 0, "复制延迟缓冲 (毫秒)", copy_delay_var)
    _add_labeled_entry(ocr_frame, 1, "复制备用重试次数", copy_retry_var)

    # === 【发音引擎】 ===
    tts_frame = ttk.LabelFrame(container, text="语音发音引擎", padding=14)
    tts_frame.pack(fill=tk.X, pady=(0, 15))
    tts_frame.columnconfigure(1, weight=1)

    _add_labeled_entry(tts_frame, 0, "单次最大朗读字符数", max_chars_var)
    _add_labeled_entry(tts_frame, 1, "语速 (默认参考~180)", tts_rate_var)
    _add_labeled_entry(tts_frame, 2, "指定发音人 (包含关键词，如 Huihui)", tts_voice_var)

    ttk.Checkbutton(
        tts_frame,
        text="如果未获取到文本，不要语音提示失败",
        variable=skip_empty_var,
    ).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
    ttk.Checkbutton(
        tts_frame,
        text="自动将提取到的英文字段翻译为中文后再朗读",
        variable=enable_translation_var,
    ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))


def _build_logs_tab(
    logs_tab: ttk.Frame,
    log_path_var: tk.StringVar,
    on_refresh: Callable[[], None],
    on_copy: Callable[[], None],
    on_open_dir: Callable[[], None],
) -> tk.Text:
    container = ttk.Frame(logs_tab, padding=14)
    container.pack(fill=tk.BOTH, expand=True)
    container.columnconfigure(1, weight=1)
    container.rowconfigure(2, weight=1)

    ttk.Label(container, text="日志文件路径:").grid(row=0, column=0, sticky=tk.W, pady=2)
    ttk.Entry(container, textvariable=log_path_var, state="readonly").grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)
    ttk.Button(container, text="打开所在文件夹", command=on_open_dir).grid(row=0, column=2, sticky=tk.E, pady=2)

    text_frame = ttk.Frame(container)
    text_frame.grid(row=2, column=0, columnspan=3, sticky=tk.NSEW, pady=(15, 10))
    text_frame.columnconfigure(0, weight=1)
    text_frame.rowconfigure(0, weight=1)

    # 黑底绿字，提供极客感
    logs_text = tk.Text(text_frame, wrap=tk.WORD, bg="#0d0d0d", fg="#4caf50", insertbackground="white")
    logs_text.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=logs_text.yview)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)
    logs_text.configure(yscrollcommand=scrollbar.set)

    button_row = ttk.Frame(container)
    button_row.grid(row=3, column=0, columnspan=3, sticky=tk.W)
    ttk.Button(button_row, text="刷新日志", command=on_refresh).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(button_row, text="一键复制全部日志", command=on_copy).pack(side=tk.LEFT)
    return logs_text


def _add_labeled_entry(
    parent: ttk.Frame,
    row: int,
    label_text: str,
    variable: tk.StringVar,
) -> None:
    ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky=tk.W, pady=6, padx=(0, 15))
    ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky=tk.EW, pady=6)


def read_log_tail(log_path: Path, max_lines: int = 500) -> str:
    if not log_path.exists():
        return f"日志文件不存在: {log_path}"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        return f"读取日志失败: {exc}"
    return "\n".join(lines[-max_lines:])


def _has_hotkey_conflict(current: AppConfig, new_config: AppConfig) -> bool:
    current_text = current.hotkey.strip().lower()
    current_screenshot = current.screenshot_hotkey.strip().lower()
    new_text = new_config.hotkey.strip().lower()
    new_screenshot = new_config.screenshot_hotkey.strip().lower()

    releasing = set()
    if new_text != current_text:
        releasing.add(current_text)
    if new_screenshot != current_screenshot:
        releasing.add(current_screenshot)

    changed_candidates: list[str] = []
    if new_text != current_text:
        changed_candidates.append(new_text)
    if new_screenshot != current_screenshot:
        changed_candidates.append(new_screenshot)

    for hotkey in changed_candidates:
        if hotkey in releasing:
            continue
        modifiers, vk = parse_hotkey(hotkey)
        if not is_hotkey_available(modifiers, vk):
            return True
    return False
