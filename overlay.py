"""
Translation display window - supports two modes:
  - "standalone": normal window with title bar, resizable
  - "overlay": borderless transparent overlay with optional click-through
"""
import ctypes
import os
import time
import tkinter as tk
from datetime import datetime
from queue import Queue, Empty
from tkinter import ttk

from config import AppConfig, VERSION

# ---- debug log (temporary) ----
def _debug_log(msg: str):
    try:
        log_path = os.path.join(os.environ.get("TEMP", "."), "ets2_translator_debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} [{os.getpid()}] {msg}\n")
    except Exception:
        pass

# Win32 constants
GWL_EXSTYLE = -20
GWLP_WNDPROC = -4
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WM_HOTKEY = 0x0312
HOTKEY_SEND_ID = 1
MOD_SHIFT = 0x0004
MOD_CONTROL = 0x0002
MOD_ALT = 0x0001

BG = "#000000"
FG = "#cccccc"


class OverlayWindow:
    """Tkinter overlay window showing translated chat messages."""

    def __init__(self, cfg: AppConfig, message_queue: Queue, stats_ref: dict = None):
        self.cfg = cfg
        self.queue = message_queue
        self.stats_ref = stats_ref or {}
        self.root = tk.Tk()
        self.root.title(f"ETS2 聊天翻译器 {VERSION}")
        self.root.configure(bg=BG)
        self._messages = []
        self._displayed_count = 0  # how many messages are currently shown
        self._is_overlay = False
        self._edge_code = ""
        self._save_pos_after = None  # after_id for debounced position save
        self._ready = False  # suppress save during init
        self._setup_ui()
        self._apply_mode()
        self._restore_or_center()
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.after(1000, lambda: setattr(self, "_ready", True))

        # Start global hotkey poller after window is ready
        self.root.after(500, self._start_hotkey_poller)

    def _setup_ui(self):
        # Outer container
        self.outer = tk.Frame(self.root, bg=BG, bd=0)
        self.outer.pack(fill=tk.BOTH, expand=True)

        # Title bar (only visible in overlay mode, used as drag handle)
        self.title_bar = tk.Frame(self.outer, bg="#181818", height=22, cursor="fleur")
        self.title_label = tk.Label(
            self.title_bar, text=f" ETS2 聊天翻译器 {VERSION}",
            bg="#181818", fg="#666666", font=("Microsoft YaHei", 9), anchor=tk.W
        )
        self.title_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.close_btn = tk.Label(
            self.title_bar, text="X ", bg="#181818", fg="#666666",
            font=("Microsoft YaHei", 10, "bold"), cursor="hand2"
        )
        self.close_btn.pack(side=tk.RIGHT)
        self.close_btn.bind("<Button-1>", lambda e: self.hide())

        # Overlay-mode mouse handlers for drag & resize (frame + title bar)
        for w in (self.outer, self.title_bar, self.title_label):
            w.bind("<Button-1>", self._on_mouse_down)
            w.bind("<B1-Motion>", self._on_mouse_move)
            w.bind("<Motion>", self._on_mouse_hover)
            w.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Pack BOTTOM elements FIRST to reserve their space

        # Stats bar (packed first, gets reserved space at bottom)
        self.stats_label = tk.Label(
            self.outer, text="", bg="#0f0f0f", fg="#555555",
            font=("Microsoft YaHei", 8), anchor=tk.W, padx=6,
            height=2,
        )
        self.stats_label.pack(side=tk.BOTTOM, fill=tk.X)

        # Input area (packed second, auto-sizes to fit children)
        self.input_frame = tk.Frame(self.outer, bg=BG)
        self.input_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # Entry row
        self.entry_row = tk.Frame(self.input_frame, bg=BG, height=32)
        self.entry_row.pack(fill=tk.X, padx=4, pady=(1, 3))
        self.send_entry = tk.Entry(
            self.entry_row, font=("Microsoft YaHei", self.cfg.font_size),
            bg="#1a1a1a", fg=FG, insertbackground=FG,
            relief=tk.FLAT, borderwidth=0,
        )
        self.send_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)
        hotkey_display = self._format_hotkey(self.cfg.send_hotkey)
        self.send_hint = tk.Label(
            self.entry_row, text=f" {hotkey_display} 呼出 ", bg=BG, fg="#888888",
            font=("Microsoft YaHei", 9),
        )
        self.send_hint.pack(side=tk.RIGHT, padx=(4, 0))
        self.send_entry.bind("<Return>", self._on_send_enter)
        self.send_entry.bind("<Escape>", lambda e: (
            self.send_entry.delete(0, tk.END), self._update_hotkey_hint()
        ))
        self.send_entry.bind("<FocusIn>", lambda e: self.send_hint.config(text=" 输入中文 "))
        self.send_entry.bind("<FocusOut>", lambda e: self._update_hotkey_hint())

        # Countdown frame (shown during send countdown, hidden otherwise)
        self.countdown_frame = tk.Frame(self.input_frame, bg=BG, height=28)
        self.countdown_label = tk.Label(
            self.countdown_frame, text="", bg=BG, fg="#f44747",
            font=("Microsoft YaHei", 10),
        )
        self.countdown_label.pack(side=tk.LEFT, padx=6)
        self.countdown_cancel = tk.Label(
            self.countdown_frame, text="[ESC 取消发送]", bg=BG, fg="#f44747",
            font=("Microsoft YaHei", 9), cursor="hand2",
        )
        self.countdown_cancel.pack(side=tk.RIGHT, padx=6)
        self.countdown_cancel.bind("<Button-1>", lambda e: (
            self.send_entry.delete(0, tk.END), self._update_hotkey_hint()
        ))

        # Sending state
        self._sending = False
        self._pending_chinese = ""
        self._pending_english = ""

        # Text area (packed LAST — gets remaining space after bottom elements)
        text_frame = tk.Frame(self.outer, bg=BG)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

        self.text = tk.Text(
            text_frame,
            font=("Microsoft YaHei", self.cfg.font_size),
            bg=BG,
            fg=FG,
            wrap=tk.WORD,
            state=tk.DISABLED,
            borderwidth=0,
            highlightthickness=0,
            padx=6, pady=4,
            insertbackground=FG,
        )
        vbar = ttk.Scrollbar(text_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=vbar.set)

        # Layout inside text_frame
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y, before=self.text)

        # Save position on window resize (standalone mode)
        self.root.bind("<Configure>", lambda e: self._schedule_save_position())

        # Resize grip triangle drawn in text widget corner
        self._grip_tag = "grip_marker"
        self.text.tag_configure(self._grip_tag, foreground="#555555",
                                font=("Microsoft YaHei", 10))

        # Text widget mouse handlers for drag & resize
        self.text.bind("<Button-1>", self._on_mouse_down)
        self.text.bind("<B1-Motion>", self._on_mouse_move)
        self.text.bind("<Motion>", self._on_mouse_hover)
        self.text.bind("<ButtonRelease-1>", self._on_mouse_up)

        # Color tags
        self.text.tag_configure("player", foreground="#569cd6",
                                font=("Microsoft YaHei", self.cfg.font_size, "bold"))
        self.text.tag_configure("original", foreground=FG)
        self.text.tag_configure("arrow", foreground="#6a6a6a")
        self.text.tag_configure("translation", foreground="#dcdcaa")
        self.text.tag_configure("self_prefix", foreground="#4ec9b0")
        self.text.tag_configure("error", foreground="#f44747")
        self.text.tag_configure("sent_prefix", foreground="#4ec9b0",
                                font=("Microsoft YaHei", self.cfg.font_size, "bold"))
        self.text.tag_configure("sent_arrow", foreground="#5a8a5a")

        # Right-click menu
        self.ctx_menu = tk.Menu(self.root, tearoff=0, bg="#222222", fg=FG)
        self.ctx_menu.add_command(label="Settings / 设置", command=self._on_settings)
        self.ctx_menu.add_command(label="Switch Mode / 切换模式", command=self._toggle_mode)
        self.ctx_menu.add_separator()
        self.ctx_menu.add_command(label="Hide / 隐藏", command=self.hide)
        self.ctx_menu.add_command(label="Exit / 退出", command=self._on_exit)
        self.text.bind("<Button-3>", lambda e: self.ctx_menu.tk_popup(e.x_root, e.y_root))

        # Callback stubs (set by main.py)
        self._settings_cb = None
        self._switch_mode_cb = None
        self._exit_cb = None

    def _restore_or_center(self):
        """Restore saved window position or center on screen."""
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        if self.cfg.win_w > 0 and self.cfg.win_h > 0 and self.cfg.win_x >= 0 and self.cfg.win_y >= 0:
            # Clamp to visible screen area
            x = max(0, min(self.cfg.win_x, sw - 100))
            y = max(0, min(self.cfg.win_y, sh - 100))
            w = min(self.cfg.win_w, sw)
            h = min(self.cfg.win_h, sh)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
        else:
            w = self.cfg.win_w if self.cfg.win_w > 0 else 620
            h = self.cfg.win_h if self.cfg.win_h > 0 else 360
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.root.geometry(f"{w}x{h}+{x}+{y}")

    def _save_position(self):
        """Save window position and size to config (debounced)."""
        if self.root.state() == "withdrawn":
            return
        try:
            g = self.root.geometry()
            # Parse "WxH+X+Y"
            size, x, y = g.replace("x", " ").replace("+", " ").split()
            self.cfg.win_w = int(size.split()[0]) if " " not in size else int(size.split()[0])
            w, x_part = g.split("+", 1)
            self.cfg.win_w, self.cfg.win_h = (int(v) for v in w.split("x"))
            parts = g.replace("x", "+").split("+")
            self.cfg.win_w = int(parts[0])
            self.cfg.win_h = int(parts[1])
            self.cfg.win_x = int(parts[2])
            self.cfg.win_y = int(parts[3])
        except (ValueError, IndexError):
            return

    def _schedule_save_position(self):
        """Debounced save: wait 1 second after last drag/resize before saving."""
        if not self._ready:
            return
        if self._save_pos_after:
            self.root.after_cancel(self._save_pos_after)
        self._save_pos_after = self.root.after(1000, self._do_save_position)

    def _do_save_position(self):
        self._save_pos_after = None
        self._save_position()
        from config import save_config
        save_config(self.cfg)

    def _apply_mode(self):
        """Apply window mode settings without resetting window size."""
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.cfg.window_opacity)

        was_visible = self.root.state() != "withdrawn"
        if was_visible:
            self.root.withdraw()

        if self.cfg.window_mode == "overlay":
            self._is_overlay = True
            self.root.resizable(False, False)
            self.root.minsize(280, 250)
            self.root.overrideredirect(True)
            self.root.update_idletasks()  # ensure new hwnd after overrideredirect
            self.title_bar.pack(side=tk.TOP, fill=tk.X)
            ex = ctypes.windll.user32.GetWindowLongPtrW(self.root.winfo_id(), GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongPtrW(self.root.winfo_id(), GWL_EXSTYLE, ex | WS_EX_TOOLWINDOW)
            self._set_click_through(self.cfg.click_through)
        else:
            self._is_overlay = False
            self.root.resizable(True, True)
            self.root.minsize(280, 250)
            self.root.overrideredirect(False)
            self.root.update_idletasks()  # ensure new hwnd after overrideredirect
            self.title_bar.pack_forget()
            ex = ctypes.windll.user32.GetWindowLongPtrW(self.root.winfo_id(), GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongPtrW(self.root.winfo_id(), GWL_EXSTYLE, ex & ~WS_EX_TOOLWINDOW & ~WS_EX_TRANSPARENT)

        if was_visible:
            self.root.deiconify()

    def _set_click_through(self, enable: bool):
        hwnd = self.root.winfo_id()
        ex = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        if enable:
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_TRANSPARENT)
        else:
            ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex & ~WS_EX_TRANSPARENT)

    def _toggle_mode(self):
        if self._switch_mode_cb:
            self._switch_mode_cb()
        else:
            if self.cfg.window_mode == "overlay":
                self.cfg.window_mode = "standalone"
            else:
                self.cfg.window_mode = "overlay"
            self._apply_mode()

    def _on_settings(self):
        if self._settings_cb:
            self._settings_cb()

    def _on_exit(self):
        if self._exit_cb:
            self._exit_cb()

    # ----- mouse handling for borderless resize & drag (overlay mode) -----
    BORDER = 8
    MIN_W, MIN_H = 280, 250

    CURSORS = {
        "n":  "size_ns",      "s":  "size_ns",
        "w":  "size_we",      "e":  "size_we",
        "nw": "size_nw_se",   "se": "size_nw_se",
        "ne": "size_ne_sw",   "sw": "size_ne_sw",
    }

    def _win_xy(self, event):
        """Convert event to window-relative coordinates."""
        return event.x_root - self.root.winfo_rootx(), event.y_root - self.root.winfo_rooty()

    def _edge(self, wx, wy):
        """Return 2-char edge code (n/s/w/e combos) or '' if not on edge."""
        w, h = self.root.winfo_width(), self.root.winfo_height()
        e = ""
        if wx <= self.BORDER: e += "w"
        elif wx >= w - self.BORDER: e += "e"
        if wy <= self.BORDER: e += "n"
        elif wy >= h - self.BORDER: e += "s"
        return e

    def _on_mouse_hover(self, event):
        if not self._is_overlay: return
        wx, wy = self._win_xy(event)
        edge = self._edge(wx, wy)
        c = self.CURSORS.get(edge, "")
        self.outer.configure(cursor=c)
        self.title_bar.configure(cursor=c if c else "fleur")

    def _on_mouse_down(self, event):
        if not self._is_overlay: return
        wx, wy = self._win_xy(event)
        self._edge_code = self._edge(wx, wy)
        self._mx = event.x_root
        self._my = event.y_root
        if not self._edge_code:
            self._start_x = self.root.winfo_x()
            self._start_y = self.root.winfo_y()

    def _on_mouse_up(self, event):
        self._edge_code = ""

    def _on_mouse_move(self, event):
        if not self._is_overlay: return
        dx = event.x_root - self._mx
        dy = event.y_root - self._my

        if self._edge_code:
            x, y = self.root.winfo_x(), self.root.winfo_y()
            w, h = self.root.winfo_width(), self.root.winfo_height()
            if "e" in self._edge_code: w = max(self.MIN_W, w + dx)
            if "s" in self._edge_code: h = max(self.MIN_H, h + dy)
            if "w" in self._edge_code:
                nw = max(self.MIN_W, w - dx)
                x += w - nw
                w = nw
            if "n" in self._edge_code:
                nh = max(self.MIN_H, h - dy)
                y += h - nh
                h = nh
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self._mx = event.x_root
            self._my = event.y_root
            self._schedule_save_position()
        else:
            x = self._start_x + event.x_root - self._mx
            y = self._start_y + event.y_root - self._my
            self.root.geometry(f"+{x}+{y}")
            self._schedule_save_position()

    # ----- message handling -----
    def add_message(self, player_name: str, original: str, translated: str, is_self: bool = False):
        self._messages.append((player_name, original, translated, is_self))
        if len(self._messages) > self.cfg.max_messages:
            trimmed = len(self._messages) - self.cfg.max_messages
            self._messages = self._messages[-self.cfg.max_messages:]
            self._displayed_count = max(0, self._displayed_count - trimmed)
        # Schedule a display sync (debounced via after_idle)
        if not hasattr(self, '_sync_scheduled') or not self._sync_scheduled:
            self._sync_scheduled = True
            self.root.after_idle(self._do_sync_and_clear)

    def _do_sync_and_clear(self):
        self._sync_scheduled = False
        self._sync_display()

    def _sync_display(self):
        """Incrementally sync the text widget with _messages.
        Only inserts new messages since last sync; avoids full redraw.
        """
        self.text.configure(state=tk.NORMAL)
        new_total = len(self._messages)

        # Messages list was trimmed (rotated) — reset display
        if new_total < self._displayed_count:
            self.text.delete("1.0", tk.END)
            self._displayed_count = 0
            if self._is_overlay:
                self.text.insert(tk.END, " ◢", self._grip_tag)

        # Insert new messages before the grip marker (if any)
        insert_pos = "end-1c" if self._is_overlay else tk.END
        for i in range(self._displayed_count, new_total):
            player, orig, trans, is_self = self._messages[i]
            self._insert_one_at(insert_pos, player, orig, trans, is_self)

        self._displayed_count = new_total

        # Trim overflow lines from the top
        max_lines = self.cfg.max_messages
        total = int(self.text.index("end-1c").split(".")[0])
        if total > max_lines:
            self.text.delete("1.0", f"{total - max_lines + 1}.0")

        self.text.configure(state=tk.DISABLED)
        self.text.see(tk.END)

    def _insert_one_at(self, pos, player: str, orig: str, trans: str, is_self: bool):
        """Insert a single message at the given position."""
        prefix = "(You) " if is_self else ""
        tags = []
        tags.append(("player", f"{prefix}["))
        tags.append(("player" if not is_self else "self_prefix", f"{player}"))
        tags.append(("player", "] "))
        tags.append(("original", f"{orig}"))
        if trans != orig:
            tags.append(("arrow", " → "))
            tag = "error" if trans.startswith("[") else "translation"
            tags.append((tag, trans))
        tags.append((None, "\n"))

        for tag, text in tags:
            if tag:
                self.text.insert(pos, text, tag)
            else:
                self.text.insert(pos, text)

    def poll_messages(self):
        while True:
            try:
                item = self.queue.get_nowait()
                if isinstance(item, tuple) and len(item) == 2:
                    msg, translated = item
                    self.add_message(msg.player_name, msg.text, translated, msg.is_self)
                    self.root.deiconify()
            except Empty:
                break
        self._update_stats()
        self.root.after(250, self.poll_messages)

    def _update_stats(self):
        if not self.stats_ref:
            return
        t = self.stats_ref.get("translated", 0)
        c = self.stats_ref.get("cached", 0)
        s = self.stats_ref.get("self", 0)
        total = t + c + s
        if total == 0:
            self.stats_label.config(text="  已翻译: 0  |  缓存命中: 0  |  跳过(自己): 0  |  节省: 0%")
            return
        saved = int((c + s) / total * 100) if total > 0 else 0
        self.stats_label.config(
            text=f"  已翻译: {t}  |  缓存命中: {c}  |  跳过(自己): {s}  |  节省: {saved}%"
        )

    # ----- global hotkey (polling-based, no WNDPROC hook needed) -----
    def _format_hotkey(self, raw: str) -> str:
        parts = [p.strip().title() for p in raw.strip().split("+")]
        return "+".join(parts)

    def _update_hotkey_hint(self):
        self.send_hint.config(
            text=f" {self._format_hotkey(self.cfg.send_hotkey)} 呼出 ",
            fg="#888888",
        )

    def _parse_hotkey(self, hotkey_str: str) -> tuple[int, int]:
        """Parse 'shift+y' into (mods_bitmask, virtual_key_code)."""
        parts = hotkey_str.lower().strip().split("+")
        mods = 0
        for p in parts[:-1]:
            p = p.strip()
            if p in ("shift", "shft"): mods |= MOD_SHIFT
            elif p in ("ctrl", "control"): mods |= MOD_CONTROL
            elif p in ("alt"): mods |= MOD_ALT
        key = parts[-1].strip()
        vk = ord(key.upper()) if len(key) == 1 else 0
        return mods, vk

    def _start_hotkey_poller(self):
        """Background thread: polls GetAsyncKeyState for the hotkey combo."""
        mods, vk = self._parse_hotkey(self.cfg.send_hotkey)
        if vk == 0:
            return

        import threading
        self._hotkey_active = True

        def poller():
            # Map modifier flags to VK codes for GetAsyncKeyState
            mod_vks = []
            if mods & MOD_SHIFT: mod_vks.append(0x10)   # VK_SHIFT
            if mods & MOD_CONTROL: mod_vks.append(0x11)  # VK_CONTROL
            if mods & MOD_ALT: mod_vks.append(0x12)      # VK_MENU

            # High bit = key currently held down
            def held(vk_code): return ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000

            was_down = False
            while getattr(self, '_hotkey_active', False):
                # All required modifiers must be held
                mods_ok = all(held(mv) for mv in mod_vks) if mod_vks else True
                key_down = held(vk)
                combo = mods_ok and key_down

                if combo and not was_down:
                    # Edge-triggered: fire on key-down transition
                    self.root.after(0, self._focus_send_entry)
                was_down = combo
                threading.Event().wait(0.05)  # 50ms poll interval

        t = threading.Thread(target=poller, daemon=True)
        t.start()

    def _stop_hotkey_poller(self):
        self._hotkey_active = False

    def _focus_send_entry(self):
        """Bring window to front and set keyboard focus to the send entry."""
        try:
            self.root.deiconify()
            self.root.lift()
            hwnd = self.root.winfo_id()

            # AttachThreadInput: bypass Windows focus-stealing restrictions
            fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
            fg_tid = ctypes.windll.user32.GetWindowThreadProcessId(fg_hwnd, 0)
            our_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            if fg_tid and fg_tid != our_tid:
                ctypes.windll.user32.AttachThreadInput(our_tid, fg_tid, True)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.AttachThreadInput(our_tid, fg_tid, False)
            else:
                ctypes.windll.user32.SetForegroundWindow(hwnd)

            self.root.focus_force()
            self.send_entry.focus_set()
            self._click_on_widget(self.send_entry)
            # Schedule a second focus attempt after window is fully painted
            self.root.after(100, lambda: self.send_entry.focus_set() if self.root.state() != "withdrawn" else None)
        except Exception:
            pass

    def update_send_hotkey(self, new_hotkey: str):
        """Called when user changes the hotkey in settings."""
        self._stop_hotkey_poller()
        self.cfg.send_hotkey = new_hotkey
        self._update_hotkey_hint()
        self._start_hotkey_poller()

    # ----- send chat message -----
    def _on_send_enter(self, event):
        if self._sending:
            return "break"
        text = self.send_entry.get().strip()
        if not text:
            return "break"

        self._sending = True
        self._pending_chinese = text
        self.send_entry.delete(0, tk.END)
        self.send_entry.config(state=tk.DISABLED)
        self.send_hint.config(text=" 翻译中... ", fg="#cccccc")

        import threading
        threading.Thread(target=self._do_translate, args=(text,), daemon=True).start()
        return "break"

    def _do_translate(self, chinese_text: str):
        from translator import translate_to_english

        try:
            english = translate_to_english(self.cfg, chinese_text)
        except Exception as e:
            self.root.after(0, lambda: self._on_translate_error(str(e)))
            return

        self.root.after(0, lambda: self._on_translate_done(chinese_text, english))

    def _on_translate_done(self, chinese: str, english: str):
        """Translation finished — put result in the entry box for manual send."""
        self._pending_chinese = chinese
        self._pending_english = english
        self._sending = False
        self.send_entry.config(state=tk.NORMAL)
        self.send_entry.delete(0, tk.END)
        self.send_entry.insert(0, english)
        self.send_entry.select_range(0, tk.END)
        self.send_entry.icursor(tk.END)
        self.send_hint.config(text=" 翻译完成 | 用热键手动发送 ", fg="#4ec9b0")
        self._start_manual_send_poller()

    def _on_translate_error(self, error: str):
        self._sending = False
        self.send_entry.config(state=tk.NORMAL)
        self.send_hint.config(text=" 翻译失败 ", fg="#f44747")
        self.root.after(5000, lambda: self._update_hotkey_hint())
        self.add_message("System", "发送翻译失败", error, is_self=True)

    # ----- manual send hotkeys -----
    _SPECIAL_VK = {
        "enter": 0x0D, "return": 0x0D,
        "esc": 0x1B, "escape": 0x1B,
        "tab": 0x09, "space": 0x20,
        "backspace": 0x08, "bs": 0x08,
        "delete": 0x2E, "del": 0x2E,
        "home": 0x24, "end": 0x23,
        "pgup": 0x21, "pgdn": 0x22,
        "left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28,
        "insert": 0x2D, "ins": 0x2D,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
        "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
        "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    }

    def _parse_hotkey_vk(self, hotkey_str: str) -> tuple[int, int]:
        """Parse hotkey string into (mods_mask, vk_code). Supports special keys."""
        parts = hotkey_str.lower().strip().split("+")
        mods = 0
        for p in parts[:-1]:
            p = p.strip()
            if p in ("shift", "shft"): mods |= MOD_SHIFT
            elif p in ("ctrl", "control"): mods |= MOD_CONTROL
            elif p in ("alt"): mods |= MOD_ALT
        key = parts[-1].strip()
        if key in self._SPECIAL_VK:
            vk = self._SPECIAL_VK[key]
        elif len(key) == 1:
            vk = ord(key.upper())
        else:
            vk = 0
        return mods, vk

    def _mod_vks(self, mods: int) -> list[int]:
        """Convert MOD_* flags to VK codes for GetAsyncKeyState."""
        vks = []
        if mods & MOD_SHIFT: vks.append(0x10)
        if mods & MOD_CONTROL: vks.append(0x11)
        if mods & MOD_ALT: vks.append(0x12)
        return vks

    def _start_manual_send_poller(self):
        """Background thread polls hotkeys: copy (detect only) and enter (mark sent)."""
        if getattr(self, '_manual_poller_active', False):
            return
        self._manual_poller_active = True

        import threading
        from ctypes import windll

        copy_mods, copy_vk = self._parse_hotkey_vk(self.cfg.copy_hotkey)
        enter_mods, enter_vk = self._parse_hotkey_vk(self.cfg.enter_hotkey)

        def held(vk_code): return windll.user32.GetAsyncKeyState(vk_code) & 0x8000

        def check(mods, vk):
            if vk == 0:
                return False
            mv = self._mod_vks(mods)
            return all(held(mv) for mv in mv) and held(vk)

        was_copy = was_enter = False

        def poller():
            nonlocal was_copy, was_enter
            while getattr(self, '_manual_poller_active', False):
                cd = check(copy_mods, copy_vk)
                ed = check(enter_mods, enter_vk)

                if cd and not was_copy:
                    self.root.after(0, self._on_copy_hotkey)
                if ed and not was_enter:
                    self.root.after(0, self._on_enter_hotkey)

                was_copy, was_enter = cd, ed
                threading.Event().wait(0.05)

        t = threading.Thread(target=poller, daemon=True)
        t.start()

    def _stop_manual_send_poller(self):
        self._manual_poller_active = False

    def _on_copy_hotkey(self):
        """Detected user pressed copy hotkey — system already copied the text."""
        if not self._pending_english:
            return
        self.send_hint.config(text=" 已复制到剪贴板 ", fg="#4ec9b0")
        self.root.after(1500, lambda: self.send_hint.config(
            text=" 翻译完成 | 用热键手动发送 ", fg="#4ec9b0"))

    def _on_enter_hotkey(self):
        """Detected user pressed enter hotkey — message was sent."""
        self._stop_manual_send_poller()
        self._insert_sent(self._pending_chinese, self._pending_english)
        self.send_hint.config(text=" 已发送 ", fg="#4ec9b0")
        self.root.after(2000, lambda: (
            self.send_entry.delete(0, tk.END),
            self._update_hotkey_hint()
        ))

    # ----- countdown frame (kept for layout, hidden by default) -----
    def _show_countdown(self):
        self.countdown_frame.pack(fill=tk.X, padx=4, pady=(0, 3))

    def _hide_countdown(self):
        self.countdown_frame.pack_forget()

    def _insert_sent(self, chinese: str, english: str):
        """Display a sent message in the chat window."""
        self._messages.append(("(Sent)", english, chinese, True))
        if len(self._messages) > self.cfg.max_messages:
            self._messages = self._messages[-self.cfg.max_messages:]
            self._displayed_count = max(0, self._displayed_count - 1)
        if not hasattr(self, '_sync_scheduled') or not self._sync_scheduled:
            self._sync_scheduled = True
            self.root.after_idle(self._do_sync_and_clear)

    def _click_on_widget(self, widget):
        """Move cursor to widget center and simulate a mouse click."""
        try:
            self.root.update_idletasks()
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() // 2
            ctypes.windll.user32.SetCursorPos(x, y)
            time.sleep(0.02)
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            time.sleep(0.02)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        except Exception:
            pass

    def hide(self):
        self._stop_hotkey_poller()
        self._save_position()
        from config import save_config
        save_config(self.cfg)
        self.root.withdraw()

    def show(self):
        self.root.deiconify()
        self._start_hotkey_poller()

    def toggle_visibility(self):
        if self.root.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    def set_opacity(self, value: float):
        self.cfg.window_opacity = value
        self.root.attributes("-alpha", value)

    def run(self):
        self.root.after(100, self.poll_messages)
        self.root.mainloop()
