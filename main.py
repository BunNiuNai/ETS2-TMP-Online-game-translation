"""
ETS2 Chat Translator - Free & Open Source
Entry point: tray icon, window management, module wiring.
"""
import threading
import tkinter as tk
from queue import Queue
from tkinter import ttk

from config import AppConfig, load_config, save_config, CONFIG_PATH, DOCUMENTS_PATH
from monitor import ChatMonitor, CHAT_LOG_DIR, log_dir_status
from overlay import OverlayWindow
from translator import Translator, test_connection

class App:
    def __init__(self):
        self.cfg = load_config()
        self.raw_queue = Queue()
        self.display_queue = Queue()

        # Shared ref for auto-detected player name
        self._self_name_ref = {"name": self.cfg.player_name}

        # Start background threads
        self.monitor = ChatMonitor(self.raw_queue, self._self_name_ref)
        self.translator = Translator(self.cfg, self.raw_queue, self.display_queue)
        self.monitor.start()
        self.translator.start()

        # Create overlay window
        self.overlay = OverlayWindow(self.cfg, self.display_queue, self.translator.stats)
        self.overlay._settings_cb = self._open_settings
        self.overlay._switch_mode_cb = self._switch_mode
        self.overlay._exit_cb = self._shutdown

        # Tray icon
        self.tray = None
        self._setup_tray()

        # Handle close
        self.overlay.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._shutting_down = False

        # Show startup status
        self.overlay.root.after(300, self._startup_status)

        # Persist auto-detected player name
        self.overlay.root.after(500, self._check_self_name)

    def _check_self_name(self):
        """Periodically check if player name was auto-detected, persist it."""
        name = self._self_name_ref.get("name", "")
        if name and name != self.cfg.player_name:
            self.cfg.player_name = name
            save_config(self.cfg)
            self.overlay.root.after(0, lambda: self.overlay.add_message(
                "System", f"已识别你的游戏ID: {name}",
                f"已自动识别你的游戏ID为 {name}，你的消息将不会被翻译。可在设置中修改。",
                is_self=True
            ))
        if not name:
            self.overlay.root.after(2000, self._check_self_name)

    def _startup_status(self):
        """Show log directory and monitor status on startup."""
        docs_path = DOCUMENTS_PATH
        status = log_dir_status()
        text = f"文档目录: {docs_path}\n聊天日志: {status}"
        self.overlay.add_message(
            "System", text, text, is_self=True
        )

    def _startup_check(self):
        """Run connectivity test on startup if API key is configured."""
        if not self.cfg.api_key:
            return
        threading.Thread(target=self._do_startup_check, daemon=True).start()

    def _do_startup_check(self):
        ok, msg = test_connection(
            self.cfg.api_endpoint, self.cfg.api_key, self.cfg.api_model
        )
        if ok:
            self.overlay.root.after(0, lambda: self.overlay.add_message(
                "System", "API 连通性测试", msg, is_self=True
            ))
        else:
            self.overlay.root.after(0, lambda: self.overlay.add_message(
                "System", "API 连通性测试失败", msg, is_self=True
            ))

    def _setup_tray(self):
        # Delay tray creation to avoid GIL race with Tkinter init (Python 3.14)
        self.overlay.root.after(1000, self._start_tray)

    def _start_tray(self):
        try:
            from tray_icon import TrayIcon

            self.tray = TrayIcon("ETS2 聊天翻译器（开源）")
            self.tray.set_menu([
                {"label": "Show/Hide 显示/隐藏", "callback": self._tray_toggle, "default": True},
                {"label": "Switch Mode 切换模式", "callback": self._tray_switch_mode},
                {"label": "Click-Through 鼠标穿透", "callback": self._tray_click_through,
                 "checked": lambda: self.cfg.click_through},
                {"label": "---"},
                {"label": "Settings 设置", "callback": self._tray_settings},
                {"label": "---"},
                {"label": "Quit 退出", "callback": self._tray_quit},
            ], default_cb=self._tray_toggle)
            self.tray.start()
        except Exception:
            pass

    def _tray_toggle(self):
        self.overlay.root.after(0, self.overlay.toggle_visibility)

    def _tray_switch_mode(self):
        self.overlay.root.after(0, self._switch_mode)

    def _tray_click_through(self):
        self.cfg.click_through = not self.cfg.click_through
        save_config(self.cfg)
        self.overlay.root.after(0, lambda: self.overlay._set_click_through(self.cfg.click_through))

    def _tray_settings(self):
        self.overlay.root.after(0, self._open_settings)

    def _tray_quit(self):
        if self.tray:
            self.tray.stop()
        self.tray = None
        self.overlay.root.after(0, self._shutdown)

    def _on_close(self):
        """Hide window instead of closing."""
        self.overlay.hide()

    def _shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self.overlay._save_position()
        save_config(self.cfg)
        if self.tray:
            self.tray.stop()
            self.tray = None
        self.monitor.stop()
        self.translator.stop()
        import time
        time.sleep(0.2)
        self.overlay.root.destroy()

    def _switch_mode(self):
        if self.cfg.window_mode == "overlay":
            self.cfg.window_mode = "standalone"
        else:
            self.cfg.window_mode = "overlay"
        save_config(self.cfg)
        self.overlay._apply_mode()

    def _open_settings(self):
        old_hotkey = self.cfg.send_hotkey
        dialog = SettingsDialog(self.overlay.root, self.cfg)
        self.overlay.root.wait_window(dialog.top)
        if dialog.result:
            self.cfg = dialog.result
            self.overlay.cfg = self.cfg  # sync overlay's config reference
            self.overlay.set_opacity(self.cfg.window_opacity)
            save_config(self.cfg)
            self.overlay._apply_mode()
            if self.cfg.send_hotkey != old_hotkey:
                self.overlay.update_send_hotkey(self.cfg.send_hotkey)

    def run(self):
        self.overlay.run()
        self._shutdown()


class HotkeyCapture(tk.Frame):
    """A label that captures a key combination when clicked."""
    def __init__(self, parent, hotkey_str: str = "", **kw):
        super().__init__(parent, **kw)
        self._hotkey = hotkey_str
        self._capturing = False
        self._label = tk.Label(self, text=self._fmt(hotkey_str),
                               bg="#2a2a2a", fg="#cccccc", relief=tk.SUNKEN,
                               font=("Microsoft YaHei", 10), padx=10, pady=4,
                               anchor=tk.CENTER, width=14, cursor="hand2")
        self._label.pack()
        self._label.bind("<Button-1>", self._start_capture)
        self._label.bind("<KeyPress>", self._on_key)
        self.configure(bg="#0a0a0a")

    @staticmethod
    def _fmt(raw: str) -> str:
        if not raw:
            return "点击设置按键"
        parts = [p.strip().title() for p in raw.strip().split("+")]
        return "+".join(parts)

    def _start_capture(self, event=None):
        self._capturing = True
        self._label.config(text="按下组合键...", bg="#3a3a3a", fg="#dcdcaa")
        self._label.focus_set()

    def _on_key(self, event):
        if not self._capturing:
            return
        # Build hotkey string from modifiers + key
        mods = []
        if event.state & 0x0001: mods.append("shift")
        if event.state & 0x0004: mods.append("ctrl")
        if event.state & 0x20000: mods.append("alt")
        key = event.keysym
        # Ignore modifier-only presses
        if key.lower() in ("shift_l", "shift_r", "control_l", "control_r", "alt_l", "alt_r"):
            return "break"
        if mods:
            hotkey = "+".join(mods) + "+" + key.lower()
        else:
            hotkey = key.lower()
        self._hotkey = hotkey
        self._capturing = False
        self._label.config(text=self._fmt(hotkey), bg="#2a2a2a", fg="#cccccc")
        return "break"

    def get(self) -> str:
        return self._hotkey

    def set_hotkey(self, hotkey_str: str):
        self._hotkey = hotkey_str
        self._label.config(text=self._fmt(hotkey_str))


class SettingsDialog:
    """Configuration dialog window."""

    def __init__(self, parent, cfg: AppConfig):
        self.cfg = cfg
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title("Settings / 设置")
        self.top.geometry("520x540")
        self.top.resizable(False, False)
        self.top.transient(parent)
        self.top.grab_set()

        self._build()
        self._load_values()

    def _build(self):
        frame = ttk.Frame(self.top, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        row = 0
        ttk.Label(frame, text="API Endpoint / API 地址:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.ep_entry = ttk.Entry(frame, width=55)
        self.ep_entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(frame, text="API Key / API 密钥:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.key_entry = ttk.Entry(frame, width=55, show="*")
        self.key_entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(frame, text="Model / 模型:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.model_entry = ttk.Entry(frame, width=55)
        self.model_entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(frame, text="Window Opacity / 窗口透明度 (0.1-1.0):").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.opacity_scale = ttk.Scale(frame, from_=0.1, to=1.0, orient=tk.HORIZONTAL)
        self.opacity_scale.grid(row=row, column=1, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(frame, text="Font Size / 字体大小:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.font_spin = ttk.Spinbox(frame, from_=8, to=24, width=10)
        self.font_spin.grid(row=row, column=1, sticky=tk.W, pady=4)
        row += 1

        ttk.Label(frame, text="Max Messages / 最大消息数:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.max_spin = ttk.Spinbox(frame, from_=10, to=200, width=10)
        self.max_spin.grid(row=row, column=1, sticky=tk.W, pady=4)
        row += 1

        ttk.Label(frame, text="Your Game Name / 你的游戏ID (可选):").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.name_entry = ttk.Entry(frame, width=55)
        self.name_entry.grid(row=row, column=1, sticky=tk.EW, pady=4)
        row += 1

        ttk.Label(frame, text="Window Mode / 窗口模式:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.mode_var = tk.StringVar(value=self.cfg.window_mode)
        mode_frame = ttk.Frame(frame)
        ttk.Radiobutton(mode_frame, text="Standalone / 标准窗口", variable=self.mode_var,
                        value="standalone").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(mode_frame, text="Overlay / 悬浮窗口", variable=self.mode_var,
                        value="overlay").pack(side=tk.LEFT, padx=4)
        mode_frame.grid(row=row, column=1, sticky=tk.W, pady=4)
        row += 1

        self.click_var = tk.BooleanVar(value=self.cfg.click_through)
        self.click_cb = ttk.Checkbutton(frame,
                        text="Click-through / 鼠标穿透 (仅悬浮模式)",
                        variable=self.click_var)
        self.click_cb.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=4)
        row += 1

        ttk.Label(frame, text="Game Chat Key / 游戏聊天键:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.hotkey_cap = HotkeyCapture(frame, self.cfg.chat_hotkey)
        self.hotkey_cap.grid(row=row, column=1, sticky=tk.W, pady=4)
        row += 1

        ttk.Label(frame, text="Focus Key / 呼出输入框热键:").grid(row=row, column=0, sticky=tk.W, pady=4)
        self.focus_cap = HotkeyCapture(frame, self.cfg.send_hotkey)
        self.focus_cap.grid(row=row, column=1, sticky=tk.W, pady=4)
        row += 1

        warning_label = tk.Label(frame,
            text="注意：绑定按键要锁定大写！",
            fg="#f44747", font=("Microsoft YaHei", 9, "bold"), anchor=tk.W)
        warning_label.grid(row=row, column=1, sticky=tk.W, pady=(0, 0))
        row += 1

        # Buttons
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=16)
        self._test_btn = ttk.Button(btn_frame, text="Test / 测试连接", command=self._test_connection)
        self._test_btn.pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Save / 保存", command=self._save).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="Cancel / 取消", command=self.top.destroy).pack(side=tk.LEFT, padx=8)
        row += 1

        self._test_status = ttk.Label(frame, text="", foreground="#cccccc")
        self._test_status.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

        frame.columnconfigure(1, weight=1)

    def _test_connection(self):
        endpoint = self.ep_entry.get().strip()
        api_key = self.key_entry.get().strip()
        model = self.model_entry.get().strip()

        if not endpoint or not api_key or not model:
            self._test_status.config(text="请先填写 API 地址、密钥和模型", foreground="#f44747")
            return

        self._test_status.config(text="正在测试连接...", foreground="#cccccc")
        self._test_btn.config(state=tk.DISABLED)

        def run_test():
            ok, msg = test_connection(endpoint, api_key, model)
            self.top.after(0, lambda: self._on_test_result(ok, msg))

        threading.Thread(target=run_test, daemon=True).start()

    def _on_test_result(self, ok, msg):
        self._test_btn.config(state=tk.NORMAL)
        color = "#4ec9b0" if ok else "#f44747"
        self._test_status.config(text=msg, foreground=color)

    def _load_values(self):
        self.ep_entry.insert(0, self.cfg.api_endpoint)
        self.key_entry.insert(0, self.cfg.api_key)
        self.model_entry.insert(0, self.cfg.api_model)
        self.name_entry.insert(0, self.cfg.player_name)
        self.opacity_scale.set(self.cfg.window_opacity)
        self.font_spin.set(str(self.cfg.font_size))
        self.max_spin.set(str(self.cfg.max_messages))

    def _save(self):
        self.result = AppConfig(
            api_endpoint=self.ep_entry.get().strip(),
            api_key=self.key_entry.get().strip(),
            api_model=self.model_entry.get().strip(),
            system_prompt=self.cfg.system_prompt,
            player_name=self.name_entry.get().strip(),
            chat_hotkey=self.hotkey_cap.get().strip().lower() or "y",
            send_hotkey=self.focus_cap.get().strip().lower() or "shift+y",
            window_opacity=float(self.opacity_scale.get()),
            font_size=int(self.font_spin.get()),
            max_messages=int(self.max_spin.get()),
            window_mode=self.mode_var.get(),
            click_through=self.click_var.get(),
        )
        self.top.destroy()


def main():
    app = App()
    if not app.cfg.api_key:
        app.overlay.root.after(500, app._open_settings)
    else:
        app.overlay.root.after(500, app._startup_check)
    app.run()


if __name__ == "__main__":
    main()
