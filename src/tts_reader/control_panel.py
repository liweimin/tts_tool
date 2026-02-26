from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from typing import Callable

from .config import AppConfig, read_config, write_config, parse_hotkey
from .hotkey import is_hotkey_available


def run_control_panel(config_path: Path, log_path: Path, tab: str = "settings") -> int:
    initial_tab = "logs" if tab == "logs" else "settings"

    root = tk.Tk()
    root.title("TTS Reader Control Panel")
    root.geometry("820x600")
    root.minsize(760, 520)

    style = ttk.Style(root)
    style.configure("Status.TLabel", foreground="#1262b3")

    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    settings_tab = ttk.Frame(notebook)
    logs_tab = ttk.Frame(notebook)
    notebook.add(settings_tab, text="Settings")
    notebook.add(logs_tab, text="Logs")

    hotkey_var = tk.StringVar(root)
    copy_delay_var = tk.StringVar(root)
    copy_retry_var = tk.StringVar(root)
    max_chars_var = tk.StringVar(root)
    tts_rate_var = tk.StringVar(root)
    tts_voice_var = tk.StringVar(root)
    skip_empty_var = tk.BooleanVar(root)
    status_var = tk.StringVar(root)

    log_path_var = tk.StringVar(root, str(log_path))
    logs_text: tk.Text | None = None

    def set_status(message: str, is_error: bool = False) -> None:
        status_var.set(("[Error] " if is_error else "") + message)

    def load_config_to_form() -> None:
        config = read_config(config_path)
        hotkey_var.set(config.hotkey)
        copy_delay_var.set(str(config.copy_delay_ms))
        copy_retry_var.set(str(config.copy_retry_count))
        max_chars_var.set(str(config.max_chars))
        tts_rate_var.set(str(config.tts_rate))
        tts_voice_var.set(config.tts_voice_contains)
        skip_empty_var.set(config.skip_if_no_text)
        set_status("Loaded current config.")

    def parse_int(raw: str, field: str, minimum: int, maximum: int | None = None) -> int:
        try:
            value = int(raw.strip())
        except Exception as exc:
            raise ValueError(f"{field} must be an integer.") from exc
        if value < minimum:
            raise ValueError(f"{field} must be >= {minimum}.")
        if maximum is not None and value > maximum:
            raise ValueError(f"{field} must be <= {maximum}.")
        return value

    def collect_config_from_form() -> AppConfig:
        hotkey = hotkey_var.get().strip().lower()
        if not hotkey:
            raise ValueError("Hotkey cannot be empty.")
        parse_hotkey(hotkey)

        copy_delay_ms = parse_int(copy_delay_var.get(), "Copy Delay (ms)", minimum=80)
        copy_retry_count = parse_int(copy_retry_var.get(), "Copy Retry Count", minimum=1, maximum=6)
        max_chars = parse_int(max_chars_var.get(), "Max Chars", minimum=10)
        tts_rate = parse_int(tts_rate_var.get(), "TTS Rate", minimum=60, maximum=400)

        return AppConfig(
            hotkey=hotkey,
            copy_delay_ms=copy_delay_ms,
            copy_retry_count=copy_retry_count,
            max_chars=max_chars,
            tts_rate=tts_rate,
            tts_voice_contains=tts_voice_var.get().strip(),
            skip_if_no_text=bool(skip_empty_var.get()),
        )

    def on_apply() -> None:
        try:
            config = collect_config_from_form()
        except ValueError as exc:
            messagebox.showerror("Invalid Config", str(exc))
            return

        current = read_config(config_path)
        if config.hotkey.strip().lower() != current.hotkey.strip().lower():
            modifiers, vk = parse_hotkey(config.hotkey)
            if not is_hotkey_available(modifiers, vk):
                messagebox.showwarning(
                    "Hotkey Conflict",
                    "快捷键已被系统或其它软件占用，请换一个组合。",
                )
                set_status("Hotkey conflict detected.", is_error=True)
                return

        write_config(config, config_path)
        set_status("配置已保存，主程序会自动生效。")
        messagebox.showinfo("Saved", "配置已保存并通知主程序自动生效。")
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
            messagebox.showinfo("Logs", "No logs to copy.")
            return
        root.clipboard_clear()
        root.clipboard_append(text)
        messagebox.showinfo("Logs", "Log text copied.")

    _build_settings_tab(
        settings_tab=settings_tab,
        hotkey_var=hotkey_var,
        copy_delay_var=copy_delay_var,
        copy_retry_var=copy_retry_var,
        max_chars_var=max_chars_var,
        tts_rate_var=tts_rate_var,
        tts_voice_var=tts_voice_var,
        skip_empty_var=skip_empty_var,
        status_var=status_var,
        on_reload=load_config_to_form,
        on_apply=on_apply,
    )
    logs_text = _build_logs_tab(
        logs_tab=logs_tab,
        log_path_var=log_path_var,
        on_refresh=refresh_logs,
        on_copy=copy_logs,
    )

    load_config_to_form()
    if initial_tab == "logs":
        refresh_logs()
        notebook.select(logs_tab)
    root.mainloop()
    return 0


def _build_settings_tab(
    settings_tab: ttk.Frame,
    hotkey_var: tk.StringVar,
    copy_delay_var: tk.StringVar,
    copy_retry_var: tk.StringVar,
    max_chars_var: tk.StringVar,
    tts_rate_var: tk.StringVar,
    tts_voice_var: tk.StringVar,
    skip_empty_var: tk.BooleanVar,
    status_var: tk.StringVar,
    on_reload: Callable[[], None],
    on_apply: Callable[[], None],
) -> None:
    container = ttk.Frame(settings_tab, padding=14)
    container.pack(fill=tk.BOTH, expand=True)
    container.columnconfigure(1, weight=1)

    _add_labeled_entry(container, 0, "Hotkey", hotkey_var)
    _add_labeled_entry(container, 1, "Copy Delay (ms)", copy_delay_var)
    _add_labeled_entry(container, 2, "Copy Retry Count", copy_retry_var)
    _add_labeled_entry(container, 3, "Max Chars", max_chars_var)
    _add_labeled_entry(container, 4, "TTS Rate", tts_rate_var)
    _add_labeled_entry(container, 5, "Voice Contains", tts_voice_var)

    ttk.Checkbutton(
        container,
        text="Skip voice hint when no selected text",
        variable=skip_empty_var,
    ).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=(8, 4))

    button_row = ttk.Frame(container)
    button_row.grid(row=7, column=0, columnspan=2, sticky=tk.W, pady=(14, 4))
    ttk.Button(button_row, text="Reload", command=on_reload).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(button_row, text="Save && Apply", command=on_apply).pack(side=tk.LEFT)

    status = ttk.Label(container, textvariable=status_var, style="Status.TLabel")
    status.grid(row=8, column=0, columnspan=2, sticky=tk.W, pady=(12, 0))


def _build_logs_tab(
    logs_tab: ttk.Frame,
    log_path_var: tk.StringVar,
    on_refresh: Callable[[], None],
    on_copy: Callable[[], None],
) -> tk.Text:
    container = ttk.Frame(logs_tab, padding=14)
    container.pack(fill=tk.BOTH, expand=True)
    container.columnconfigure(0, weight=1)
    container.rowconfigure(2, weight=1)

    ttk.Label(container, text="Log File").grid(row=0, column=0, sticky=tk.W)
    ttk.Label(container, textvariable=log_path_var).grid(row=1, column=0, sticky=tk.W)

    text_frame = ttk.Frame(container)
    text_frame.grid(row=2, column=0, sticky=tk.NSEW, pady=(10, 8))
    text_frame.columnconfigure(0, weight=1)
    text_frame.rowconfigure(0, weight=1)

    logs_text = tk.Text(text_frame, wrap=tk.WORD)
    logs_text.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=logs_text.yview)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)
    logs_text.configure(yscrollcommand=scrollbar.set)

    button_row = ttk.Frame(container)
    button_row.grid(row=3, column=0, sticky=tk.W)
    ttk.Button(button_row, text="Refresh", command=on_refresh).pack(side=tk.LEFT, padx=(0, 8))
    ttk.Button(button_row, text="Copy All", command=on_copy).pack(side=tk.LEFT)
    return logs_text


def _add_labeled_entry(
    parent: ttk.Frame,
    row: int,
    label: str,
    variable: tk.StringVar,
) -> None:
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4, padx=(0, 10))
    ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky=tk.EW, pady=4)


def read_log_tail(log_path: Path, max_lines: int = 500) -> str:
    if not log_path.exists():
        return f"Log file not found: {log_path}"
    try:
        lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as exc:
        return f"Failed to read logs: {exc}"
    return "\n".join(lines[-max_lines:])
