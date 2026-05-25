"""
ETS2 Chat Translator - Free & Open Source
Entry point: tray icon, window management, module wiring.
"""
import ctypes
import sys
import threading
import tkinter as tk
from queue import Queue
from tkinter import ttk

from config import AppConfig, load_config, save_config, CONFIG_PATH, DOCUMENTS_PATH
from monitor import ChatMonitor, CHAT_LOG_DIR, log_dir_status
from overlay import OverlayWindow

# ---- single-instance lock ----
_SINGLE_MUTEX_NAME = "Global\\ETS2_Chat_Translator_SingleInstance"


def _ensure_single_instance():
    """Create a named Windows mutex. If it already exists, bring the existing
    window to front and exit this process. Returns True if this is the first instance."""
    ctypes.windll.kernel32.CreateMutexW(None, True, _SINGLE_MUTEX_NAME)
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        # Find and restore the existing window
        hwnd = ctypes.windll.user32.FindWindowW(None, None)
        # Generic approach: just alert and exit
        ctypes.windll.user32.MessageBoxW(0,
            "ETS2 聊天翻译器已经在运行中。\n请查看系统托盘图标。", "ETS2 Translator", 0x40)
        return False
    return True
from translator import Translator, test_connection, test_baidu_connection
from config import VERSION
import update as updater

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
        self.overlay._check_update_cb = lambda: self._check_for_update(auto_download=True)

        # Tray icon
        self.tray = None
        self._setup_tray()

        # Handle close
        self.overlay.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._shutting_down = False

        # Show startup status
        self.overlay.root.after(300, self._startup_status)

        # Check for updates (background)
        self.overlay.root.after(1500, self._check_for_update)

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
        """Run connectivity test on startup if credentials are configured."""
        threading.Thread(target=self._do_startup_check, daemon=True).start()

    def _do_startup_check(self):
        backend = self.cfg.translation_backend
        if backend == "baidu":
            ok, msg = test_baidu_connection(self.cfg.baidu_appid, self.cfg.baidu_secret)
        elif backend == "llm+baidu":
            ok1, msg1 = test_connection(
                self.cfg.api_endpoint, self.cfg.api_key, self.cfg.api_model
            )
            ok2, msg2 = test_baidu_connection(self.cfg.baidu_appid, self.cfg.baidu_secret)
            ok = ok1 and ok2
            msg = f"LLM: {msg1}\n百度: {msg2}"
        else:
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

    def _check_for_update(self, auto_download=False):
        """Check GitHub for new releases in background thread.
        If auto_download=True and update found, start download immediately."""
        self.overlay.add_message(
            "System", "正在检查更新...", f"当前版本: {VERSION}", is_self=True
        )

        def _do_check():
            has_update, latest, url = updater.check_for_update()
            if has_update:
                if auto_download:
                    self.overlay.root.after(0, lambda: self._start_update(url, latest))
                else:
                    self.overlay.root.after(0, lambda: self.overlay.add_message(
                        "System",
                        f"发现新版本 {latest}！",
                        f"当前 {VERSION} → 最新 {latest}\n右键菜单 → 检查更新 即可自动下载更新",
                        is_self=True
                    ))
            elif latest:
                self.overlay.root.after(0, lambda: self.overlay.add_message(
                    "System", f"已是最新版本 {latest}", f"当前版本: {VERSION}", is_self=True
                ))
            else:
                self.overlay.root.after(0, lambda: self.overlay.add_message(
                    "System", "更新检查失败", "无法连接到 GitHub，请检查网络", is_self=True
                ))

        threading.Thread(target=_do_check, daemon=True).start()

    def _start_update(self, url=None, latest=None):
        """Download and apply update, with progress shown in overlay."""
        if not url:
            has_update, latest, url = updater.check_for_update()
            if not has_update:
                self.overlay.add_message(
                    "System", f"已是最新版本 {latest}", "无需更新", is_self=True
                )
                return

        self.overlay.add_message(
            "System", f"开始下载 {latest or ''} ...", "下载中 0%", is_self=True
        )

        def on_progress(pct):
            if pct < 0:
                self.overlay.root.after(0, lambda: self.overlay.add_message(
                    "System", "下载失败", "请检查网络后重试", is_self=True
                ))
            else:
                self.overlay.root.after(0, lambda p=pct: self.overlay._update_last_sys_msg(
                    f"下载中 {p}%"
                ))

        def _do_download():
            new_exe = updater.download_update(url, on_progress)
            if new_exe:
                self.overlay.root.after(0, lambda: self.overlay.add_message(
                    "System", "下载完成，正在更新...",
                    "应用将在更新后自动重启", is_self=True
                ))
                self.overlay.root.after(500, lambda: self._apply_update(new_exe))

        threading.Thread(target=_do_download, daemon=True).start()

    def _apply_update(self, new_exe_path: str):
        """Replace current exe and restart."""
        own_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
        if not own_path.lower().endswith('.exe'):
            self.overlay.add_message(
                "System", "开发模式无法自动更新",
                "请手动从 GitHub Releases 下载新版本", is_self=True
            )
            return
        updater.apply_update(new_exe_path, own_path)
        self._shutdown()
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
        dialog = SettingsDialog(self.overlay.root, self.cfg, self.overlay)
        self.overlay.root.wait_window(dialog.top)
        if dialog.result:
            self.cfg = dialog.result
            self.overlay.cfg = self.cfg  # sync overlay's config reference
            self.overlay.set_opacity(self.cfg.window_opacity)
            self.overlay.set_font_size(self.cfg.font_size)
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
        self._label = tk.Label(self, text=self._fmt(hotkey_str),
                               bg="#21262d", fg="#e6edf3", relief=tk.FLAT,
                               font=("Microsoft YaHei", 10), padx=12, pady=5,
                               anchor=tk.CENTER, width=14, cursor="hand2",
                               highlightthickness=1, highlightbackground="#30363d")
        self._label.pack()
        self._label.bind("<Button-1>", self._start_capture)
        self._label.bind("<KeyPress>", self._on_key)
        self.configure(bg="#161b22")

    @staticmethod
    def _fmt(raw: str) -> str:
        if not raw:
            return "点击设置按键"
        parts = [p.strip().title() for p in raw.strip().split("+")]
        return "+".join(parts)

    def _start_capture(self, event=None):
        self._capturing = True
        self._label.config(text="按下组合键...", bg="#1f6feb", fg="#ffffff",
                           highlightbackground="#58a6ff", highlightthickness=2)
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
        self._label.config(text=self._fmt(hotkey), bg="#21262d", fg="#e6edf3",
                           highlightbackground="#30363d", highlightthickness=1)
        return "break"

    def get(self) -> str:
        return self._hotkey

    def set_hotkey(self, hotkey_str: str):
        self._hotkey = hotkey_str
        self._label.config(text=self._fmt(hotkey_str), bg="#21262d", fg="#e6edf3")


class SettingsDialog:
    """Configuration dialog with Apple liquid-glass inspired design."""

    # ---- color palette (dark theme) ----
    _PAGE_BG = "#0d1117"
    _CARD_BG = "#161b22"
    _CARD_BORDER = "#30363d"
    _TEXT = "#e6edf3"
    _TEXT_SEC = "#8b949e"
    _ACCENT = "#58a6ff"
    _ACCENT_HOVER = "#79c0ff"
    _GREEN = "#3fb950"
    _RED = "#f85149"
    _INPUT_BG = "#0d1117"
    _INPUT_BORDER = "#30363d"
    _SEP = "#21262d"

    def __init__(self, parent, cfg: AppConfig, overlay=None):
        self.cfg = cfg
        self.overlay = overlay
        self._orig_opacity = cfg.window_opacity
        self._orig_mode = cfg.window_mode
        self.result = None
        self.top = tk.Toplevel(parent)
        self.top.title("Settings / 设置")
        sw = cfg.settings_win_w if cfg and getattr(cfg, "settings_win_w", 0) > 0 else 540
        sh = cfg.settings_win_h if cfg and getattr(cfg, "settings_win_h", 0) > 0 else 700
        self.top.geometry(f"{sw}x{sh}")
        self.top.minsize(420, 440)
        self.top.resizable(True, True)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.configure(bg=self._PAGE_BG)

        self._build()
        self._load_values()

        # Restore original opacity if dialog closed without saving
        self.top.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    #  ui helpers
    # ------------------------------------------------------------------
    def _card(self, parent, **kw):
        """Return a white Frame that looks like a rounded card."""
        card = tk.Frame(parent, bg=self._CARD_BG,
                        highlightbackground=self._CARD_BORDER,
                        highlightthickness=1, **kw)
        return card

    def _label(self, parent, text, accent=False, small=False, **kw):
        """Styled label."""
        fg = self._ACCENT if accent else self._TEXT
        fn = ("Microsoft YaHei", 9) if small else ("Microsoft YaHei", 10)
        return tk.Label(parent, text=text, bg=self._CARD_BG, fg=fg,
                        font=fn, anchor=tk.W, **kw)

    def _entry(self, parent, show=None, width=48):
        """Styled flat entry."""
        e = tk.Entry(parent, font=("Microsoft YaHei", 10),
                     bg=self._INPUT_BG, fg=self._TEXT,
                     insertbackground=self._TEXT,
                     relief=tk.FLAT, highlightthickness=1,
                     highlightbackground=self._INPUT_BORDER,
                     highlightcolor=self._ACCENT,
                     width=width, show=show)
        e.bind("<FocusIn>", lambda ev: e.configure(highlightbackground=self._ACCENT, highlightthickness=2))
        e.bind("<FocusOut>", lambda ev: e.configure(highlightbackground=self._INPUT_BORDER, highlightthickness=1))
        return e

    def _pill_btn(self, parent, text, command, accent=True):
        """Pill-shaped label button."""
        bg = self._ACCENT if accent else "#21262d"
        fg = "#ffffff" if accent else self._TEXT
        hov = self._ACCENT_HOVER if accent else "#30363d"
        lb = tk.Label(parent, text=text, bg=bg, fg=fg,
                       font=("Microsoft YaHei", 10),
                       padx=18, pady=7, cursor="hand2")
        lb.bind("<Enter>", lambda e: lb.configure(bg=hov))
        lb.bind("<Leave>", lambda e: lb.configure(bg=bg))
        lb.bind("<Button-1>", lambda e: command())
        return lb

    def _section_label(self, parent, text):
        """Section title with accent bar prefix."""
        lbl = tk.Label(parent, text=f"│ {text}", bg=self._PAGE_BG, fg=self._TEXT_SEC,
                        font=("Microsoft YaHei", 9, "bold"), anchor=tk.W)
        return lbl

    def _row(self, card, r, label_text, widget, extra=None):
        """Place a label + widget row inside a card. Returns next row index."""
        self._label(card, label_text).grid(row=r, column=0, sticky=tk.W,
                                            pady=5, padx=(16, 8))
        if extra:
            sub = tk.Frame(card, bg=self._CARD_BG)
            sub.columnconfigure(0, weight=1)
            widget.grid(row=0, column=0, sticky=tk.EW, pady=5)
            extra.grid(row=0, column=1, sticky=tk.E, pady=5, padx=(8, 0))
            sub.grid(row=r, column=1, sticky=tk.EW, padx=(0, 16))
            return r + 1
        widget.grid(row=r, column=1, sticky=tk.EW, pady=5, padx=(0, 16))
        return r + 1

    # ------------------------------------------------------------------
    #  build
    # ------------------------------------------------------------------
    def _build(self):
        page_bg = self._PAGE_BG

        # ---- ttk dark theme styling ----
        style = ttk.Style()
        style.theme_use("clam")  # custom-drawn theme, respects all color options
        style.configure("Vertical.TScrollbar",
                        background="#161b22", troughcolor="#0d1117",
                        arrowcolor="#8b949e", bordercolor="#161b22",
                        gripcount=0, darkcolor="#30363d", lightcolor="#30363d")
        style.map("Vertical.TScrollbar",
                  background=[("active", "#30363d"), ("pressed", "#484f58")])
        style.configure("TSpinbox",
                        fieldbackground="#0d1117", background="#21262d",
                        foreground="#e6edf3", bordercolor="#30363d",
                        darkcolor="#30363d", lightcolor="#30363d",
                        arrowcolor="#8b949e", selectbackground="#1f6feb",
                        selectforeground="#ffffff")
        style.map("TSpinbox",
                  fieldbackground=[("readonly", "#0d1117")],
                  background=[("active", "#30363d")])
        style.configure("TCombobox",
                        fieldbackground="#0d1117", background="#21262d",
                        foreground="#e6edf3", bordercolor="#30363d",
                        darkcolor="#30363d", lightcolor="#30363d",
                        arrowcolor="#8b949e", selectbackground="#1f6feb",
                        selectforeground="#ffffff")
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#0d1117")],
                  background=[("active", "#30363d"), ("hover", "#30363d")])
        # Combobox dropdown listbox (tk.Listbox, not ttk) — dark theme via option_add
        self.top.option_add("*TCombobox*Listbox.background", "#161b22")
        self.top.option_add("*TCombobox*Listbox.foreground", "#e6edf3")
        self.top.option_add("*TCombobox*Listbox.selectBackground", "#1f6feb")
        self.top.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        style.configure("TScrollbar",
                        background="#161b22", troughcolor="#0d1117",
                        arrowcolor="#8b949e", bordercolor="#161b22")

        # ---- outer scrollable area ----
        outer = tk.Frame(self.top, bg=page_bg)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.rowconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg=page_bg, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        frame = tk.Frame(canvas, bg=page_bg, padx=20, pady=16)
        frame.columnconfigure(0, weight=1)
        frame_id = canvas.create_window((0, 0), window=frame, anchor=tk.NW)

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frame.bind("<Configure>", _on_frame_configure)

        def _on_canvas_configure(event):
            canvas.itemconfig(frame_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        def _on_destroy(event):
            canvas.unbind_all("<MouseWheel>")
        self.top.bind("<Destroy>", _on_destroy)

        # ====================  Card 1: API  ====================
        self._section_label(frame, "TRANSLATION API  /  翻译接口").pack(
            fill=tk.X, pady=(0, 8))
        card1 = self._card(frame, padx=16, pady=12)
        card1.pack(fill=tk.X, pady=(0, 4))
        card1.columnconfigure(1, weight=1)

        r = 0
        self.ep_entry = self._entry(card1)
        r = self._row(card1, r, "API Endpoint / 地址", self.ep_entry)

        self.key_entry = self._entry(card1, show="*")
        r = self._row(card1, r, "API Key / 密钥", self.key_entry)

        self.model_entry = self._entry(card1)
        r = self._row(card1, r, "Model / 模型", self.model_entry)

        self.backend_var = tk.StringVar(value=self.cfg.translation_backend)
        self.backend_combo = ttk.Combobox(
            card1, textvariable=self.backend_var,
            values=["llm", "baidu", "llm+baidu"],
            state="readonly", width=18,
            font=("Microsoft YaHei", 10))
        self.backend_combo.bind("<<ComboboxSelected>>", self._on_backend_changed)
        r = self._row(card1, r, "Backend / 翻译后端", self.backend_combo)

        # Baidu sub-card
        self.baidu_group = tk.Frame(card1, bg=self._INPUT_BG,
                                     highlightbackground=self._CARD_BORDER,
                                     highlightthickness=1)
        self.baidu_group.columnconfigure(1, weight=1)
        tk.Label(self.baidu_group, text="Baidu Translate",
                 bg=self._INPUT_BG, fg=self._TEXT_SEC,
                 font=("Microsoft YaHei", 8, "bold"), anchor=tk.W).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, padx=12, pady=(8, 2))
        self.baidu_appid_entry = self._entry(self.baidu_group, width=42)
        self.baidu_appid_entry.grid(row=1, column=0, columnspan=2, sticky=tk.EW,
                                     padx=12, pady=(4, 2))
        tk.Label(self.baidu_group, text="APP ID",
                 bg=self._INPUT_BG, fg=self._TEXT_SEC,
                 font=("Microsoft YaHei", 8), anchor=tk.W).grid(
            row=2, column=0, sticky=tk.W, padx=12, pady=(0, 2))
        self.baidu_secret_entry = self._entry(self.baidu_group, show="*", width=42)
        self.baidu_secret_entry.grid(row=3, column=0, columnspan=2, sticky=tk.EW,
                                      padx=12, pady=(4, 2))
        tk.Label(self.baidu_group, text="Secret / 密钥",
                 bg=self._INPUT_BG, fg=self._TEXT_SEC,
                 font=("Microsoft YaHei", 8), anchor=tk.W).grid(
            row=4, column=0, sticky=tk.W, padx=12, pady=(0, 2))
        tk.Label(self.baidu_group,
                 text="免费申请  fanyi-api.baidu.com  ·  标准版每月 500 万字符",
                 bg=self._INPUT_BG, fg=self._TEXT_SEC,
                 font=("Microsoft YaHei", 7)).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=12, pady=(2, 10))
        self.baidu_group.grid(row=r, column=0, columnspan=2, sticky=tk.EW,
                               padx=12, pady=(6, 12))
        self._on_backend_changed()

        # ====================  Card 2: Hotkeys  ====================
        self._section_label(frame, "HOTKEYS  /  快捷键").pack(
            fill=tk.X, pady=(20, 8))
        card2 = self._card(frame, padx=16, pady=12)
        card2.pack(fill=tk.X, pady=(0, 4))
        card2.columnconfigure(1, weight=1)

        r = 0
        r = self._row(card2, r, "Copy Hotkey / 复制", self._hotkey_capture(card2, self.cfg.copy_hotkey, "_copy_cap"))

        r = self._row(card2, r, "Send Hotkey / 发送", self._hotkey_capture(card2, self.cfg.enter_hotkey, "_enter_cap"))

        r = self._row(card2, r, "Focus Key / 呼出输入框", self._hotkey_capture(card2, self.cfg.send_hotkey, "_focus_cap"))

        tk.Label(card2,
                 text="按下组合键进行捕获",
                 bg=self._CARD_BG, fg=self._RED,
                 font=("Microsoft YaHei", 8), anchor=tk.W).grid(
            row=r, column=1, sticky=tk.W, padx=(0, 16), pady=(4, 12))

        # ====================  Card 3: Appearance  ====================
        self._section_label(frame, "APPEARANCE  /  外观").pack(
            fill=tk.X, pady=(20, 8))
        card3 = self._card(frame, padx=16, pady=12)
        card3.pack(fill=tk.X, pady=(0, 4))
        card3.columnconfigure(1, weight=1)

        r = 0
        # Opacity row – manual layout (scale + live value label)
        self._label(card3, "Window Opacity / 窗口透明度").grid(
            row=r, column=0, sticky=tk.W, pady=5, padx=(16, 8))
        opacity_row = tk.Frame(card3, bg=self._CARD_BG)
        opacity_row.columnconfigure(0, weight=1)
        self.opacity_scale = tk.Scale(opacity_row, from_=0.1, to=1.0, resolution=0.01,
                                       orient=tk.HORIZONTAL, bg=self._CARD_BG, fg=self._TEXT,
                                       highlightthickness=0, bd=0, length=200,
                                       troughcolor="#21262d", activebackground=self._ACCENT,
                                       command=self._on_opacity_change)
        self.opacity_scale.grid(row=0, column=0, sticky=tk.EW)
        self.opacity_val = tk.Label(opacity_row, text="0.80", bg=self._CARD_BG,
                                     fg=self._ACCENT, font=("Microsoft YaHei", 10, "bold"),
                                     width=4, anchor=tk.E)
        self.opacity_val.grid(row=0, column=1, sticky=tk.E, padx=(10, 0))
        opacity_row.grid(row=r, column=1, sticky=tk.EW, padx=(0, 16))
        r += 1

        self.font_spin = ttk.Spinbox(card3, from_=8, to=24, width=6, font=("Microsoft YaHei", 10))
        r = self._row(card3, r, "Font Size / 字体大小", self.font_spin)

        self.max_spin = ttk.Spinbox(card3, from_=10, to=200, width=6, font=("Microsoft YaHei", 10))
        r = self._row(card3, r, "Max Messages / 最大消息数", self.max_spin)

        self.name_entry = self._entry(card3)
        r = self._row(card3, r, "Game Name / 游戏 ID", self.name_entry)

        self.mode_var = tk.StringVar(value=self.cfg.window_mode)
        mode_frame = tk.Frame(card3, bg=self._CARD_BG)
        for val, lbl in [("standalone", "Standalone / 标准"), ("overlay", "Overlay / 悬浮")]:
            rb = tk.Radiobutton(mode_frame, text=lbl, variable=self.mode_var, value=val,
                                bg=self._CARD_BG, fg=self._TEXT,
                                font=("Microsoft YaHei", 10),
                                selectcolor=self._CARD_BG,
                                activebackground=self._CARD_BG,
                                activeforeground=self._ACCENT,
                                command=self._on_mode_changed)
            rb.pack(side=tk.LEFT, padx=(0, 12))
        r = self._row(card3, r, "Window Mode / 窗口模式", mode_frame)

        self.click_var = tk.BooleanVar(value=self.cfg.click_through)
        cb = tk.Checkbutton(card3, text="Click-through / 鼠标穿透 (仅悬浮模式)",
                            variable=self.click_var,
                            bg=self._CARD_BG, fg=self._TEXT,
                            font=("Microsoft YaHei", 10),
                            selectcolor=self._CARD_BG,
                            activebackground=self._CARD_BG,
                            activeforeground=self._ACCENT)
        cb.grid(row=r, column=0, columnspan=2, sticky=tk.W, padx=16, pady=(4, 12))

        # ====================  Bottom buttons  ====================
        btn_row = tk.Frame(frame, bg=page_bg)
        btn_row.pack(fill=tk.X, pady=(24, 8))

        self._test_btn = self._pill_btn(btn_row, "Test / 测试连接",
                                         self._test_connection, accent=False)
        self._test_btn.pack(side=tk.LEFT, padx=(0, 8))

        self._test_status = tk.Label(btn_row, text="", bg=page_bg, fg=self._TEXT_SEC,
                                      font=("Microsoft YaHei", 9), anchor=tk.W)
        self._test_status.pack(side=tk.LEFT, padx=8, fill=tk.X, expand=True)

        self._pill_btn(btn_row, "Cancel / 取消", self._on_close, accent=False).pack(
            side=tk.RIGHT, padx=4)
        self._pill_btn(btn_row, "Save / 保存", self._save, accent=True).pack(
            side=tk.RIGHT, padx=4)

        frame.columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    #  hotkey capture helper
    # ------------------------------------------------------------------
    def _hotkey_capture(self, parent, hotkey_str, attr_name):
        cap = HotkeyCapture(parent, hotkey_str)
        setattr(self, attr_name, cap)
        cap.configure(bg=self._CARD_BG)
        return cap

    def _on_opacity_change(self, val):
        v = float(val)
        self.opacity_val.config(text=f"{v:.2f}")
        if self.overlay:
            self.overlay.set_opacity(v)

    def _on_mode_changed(self):
        if self.overlay:
            self.overlay.cfg.window_mode = self.mode_var.get()
            self.overlay._apply_mode()

    def _on_close(self):
        if self.overlay:
            self.overlay.set_opacity(self._orig_opacity)
            if self._orig_mode != self.mode_var.get():
                self.overlay.cfg.window_mode = self._orig_mode
                self.overlay._apply_mode()
        self.top.destroy()

    # ------------------------------------------------------------------
    #  the rest is unchanged
    # ------------------------------------------------------------------
    def _on_backend_changed(self, event=None):
        backend = self.backend_var.get()
        if backend in ("baidu", "llm+baidu"):
            self.baidu_group.grid()
        else:
            self.baidu_group.grid_remove()

    def _test_connection(self):
        backend = self.backend_var.get()
        if backend in ("baidu", "llm+baidu"):
            appid = self.baidu_appid_entry.get().strip()
            secret = self.baidu_secret_entry.get().strip()
            if not appid or not secret:
                self._test_status.config(text="请先填写百度 APP ID 和密钥", fg=self._RED)
                return
        if backend in ("llm", "llm+baidu"):
            endpoint = self.ep_entry.get().strip()
            api_key = self.key_entry.get().strip()
            model = self.model_entry.get().strip()
            if not endpoint or not api_key or not model:
                self._test_status.config(text="请先填写 API 地址、密钥和模型", fg=self._RED)
                return

        self._test_status.config(text="正在测试连接...", fg=self._TEXT_SEC)
        self._test_btn.configure(state=tk.DISABLED)

        def run_test():
            if backend == "llm+baidu":
                ok1, msg1 = test_connection(
                    self.ep_entry.get().strip(),
                    self.key_entry.get().strip(),
                    self.model_entry.get().strip())
                ok2, msg2 = test_baidu_connection(
                    self.baidu_appid_entry.get().strip(),
                    self.baidu_secret_entry.get().strip())
                ok = ok1 and ok2
                msg = f"LLM: {msg1}\n百度: {msg2}"
            elif backend == "baidu":
                ok, msg = test_baidu_connection(
                    self.baidu_appid_entry.get().strip(),
                    self.baidu_secret_entry.get().strip())
            else:
                ok, msg = test_connection(
                    self.ep_entry.get().strip(),
                    self.key_entry.get().strip(),
                    self.model_entry.get().strip())
            self.top.after(0, lambda: self._on_test_result(ok, msg))

        threading.Thread(target=run_test, daemon=True).start()

    def _on_test_result(self, ok, msg):
        self._test_btn.configure(state=tk.NORMAL)
        self._test_status.config(text=msg, fg=self._GREEN if ok else self._RED)

    def _load_values(self):
        self.ep_entry.insert(0, self.cfg.api_endpoint)
        self.key_entry.insert(0, self.cfg.api_key)
        self.model_entry.insert(0, self.cfg.api_model)
        self.name_entry.insert(0, self.cfg.player_name)
        self.opacity_scale.set(self.cfg.window_opacity)
        self._on_opacity_change(self.cfg.window_opacity)
        self.font_spin.set(str(self.cfg.font_size))
        self.max_spin.set(str(self.cfg.max_messages))
        self.backend_var.set(self.cfg.translation_backend)
        self.baidu_appid_entry.insert(0, self.cfg.baidu_appid)
        self.baidu_secret_entry.insert(0, self.cfg.baidu_secret)
        self._on_backend_changed()

    def _save(self):
        self.result = AppConfig(
            api_endpoint=self.ep_entry.get().strip(),
            api_key=self.key_entry.get().strip(),
            api_model=self.model_entry.get().strip(),
            system_prompt=self.cfg.system_prompt,
            player_name=self.name_entry.get().strip(),
            copy_hotkey=self._copy_cap.get().strip().lower() or "ctrl+c",
            enter_hotkey=self._enter_cap.get().strip().lower() or "enter",
            send_hotkey=self._focus_cap.get().strip().lower() or "shift+y",
            window_opacity=float(self.opacity_scale.get()),
            font_size=int(self.font_spin.get()),
            max_messages=int(self.max_spin.get()),
            window_mode=self.mode_var.get(),
            click_through=self.click_var.get(),
            translation_backend=self.backend_var.get(),
            baidu_appid=self.baidu_appid_entry.get().strip(),
            baidu_secret=self.baidu_secret_entry.get().strip(),
        )
        # Save settings dialog size
        try:
            g = self.top.geometry()
            w, rest = g.split("x", 1)
            h = rest.split("+")[0].split("-")[0]
            self.result.settings_win_w = int(w)
            self.result.settings_win_h = int(h)
        except (ValueError, IndexError):
            pass
        self.top.destroy()


def main():
    if not _ensure_single_instance():
        sys.exit(0)

    app = App()
    need_setup = False
    backend = app.cfg.translation_backend
    if backend == "baidu":
        if not app.cfg.baidu_appid or not app.cfg.baidu_secret:
            need_setup = True
    elif backend == "llm+baidu":
        if not app.cfg.api_key or not app.cfg.baidu_appid or not app.cfg.baidu_secret:
            need_setup = True
    else:
        if not app.cfg.api_key:
            need_setup = True

    if need_setup:
        app.overlay.root.after(500, app._open_settings)
    else:
        app.overlay.root.after(500, app._startup_check)
    app.run()


if __name__ == "__main__":
    main()
