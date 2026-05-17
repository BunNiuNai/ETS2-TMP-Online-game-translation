"""
Keyboard simulation and send sequence for in-game chat.
Uses Win32 SendInput API for reliable key injection.
"""
import ctypes
import ctypes.wintypes
import os
import time
import threading
from datetime import datetime

def _debug_log(msg: str):
    try:
        log_path = os.path.join(os.environ.get("TEMP", "."), "ets2_translator_debug.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().strftime('%H:%M:%S.%f')[:-3]} [{os.getpid()}] {msg}\n")
    except Exception:
        pass

# --- Win32 clipboard API type declarations (64-bit safe) ---
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

_user32.OpenClipboard.argtypes = [ctypes.wintypes.HWND]
_user32.OpenClipboard.restype = ctypes.wintypes.BOOL
_user32.EmptyClipboard.argtypes = []
_user32.EmptyClipboard.restype = ctypes.wintypes.BOOL
_user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.wintypes.HANDLE]
_user32.SetClipboardData.restype = ctypes.wintypes.HANDLE
_user32.CloseClipboard.argtypes = []
_user32.CloseClipboard.restype = ctypes.wintypes.BOOL
_user32.GetClipboardData.argtypes = [ctypes.c_uint]
_user32.GetClipboardData.restype = ctypes.wintypes.HANDLE

_kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
_kernel32.GlobalAlloc.restype = ctypes.wintypes.HGLOBAL
_kernel32.GlobalLock.argtypes = [ctypes.wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.wintypes.LPVOID
_kernel32.GlobalUnlock.argtypes = [ctypes.wintypes.HGLOBAL]
_kernel32.GlobalUnlock.restype = ctypes.wintypes.BOOL


# Win32 constants
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
VK_CONTROL = 0x11
VK_V = 0x56
VK_ESCAPE = 0x1B

# Key name to VK code mapping
KEY_NAME_MAP = {
    "enter": VK_RETURN,
    "return": VK_RETURN,
    "esc": VK_ESCAPE,
    "escape": VK_ESCAPE,
    "ctrl": VK_CONTROL,
    "control": VK_CONTROL,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "bs": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pgup": 0x21,
    "pgdn": 0x22,
    "left": 0x25,
    "right": 0x27,
    "up": 0x26,
    "down": 0x28,
    "insert": 0x2D,
    "ins": 0x2D,
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.wintypes.WPARAM),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.wintypes.WPARAM),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


def _vk_code(key: str) -> int:
    """Convert a key string to virtual key code."""
    key_lower = key.lower().strip()
    if key_lower in KEY_NAME_MAP:
        return KEY_NAME_MAP[key_lower]
    if len(key_lower) == 1:
        return ord(key_lower.upper())
    return ord(key_lower.upper()) if key_lower else 0


def _send_key(vk: int, key_up: bool = False):
    """Send a single keyboard input event."""
    flags = KEYEVENTF_KEYUP if key_up else 0
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.u.ki.wVk = vk
    inp.u.ki.wScan = 0
    inp.u.ki.dwFlags = flags
    inp.u.ki.time = 0
    inp.u.ki.dwExtraInfo = 0
    ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


def _press_key(vk: int, hold_sec: float = 0.05):
    """Press and release a key."""
    _send_key(vk, key_up=False)
    time.sleep(hold_sec)
    _send_key(vk, key_up=True)


def _combo(keys: list[int], hold_sec: float = 0.05):
    """Press multiple keys together (like Ctrl+V)."""
    for vk in keys:
        _send_key(vk, key_up=False)
    time.sleep(hold_sec)
    for vk in reversed(keys):
        _send_key(vk, key_up=True)


# Modifier VK constants
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_ALT = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_MOD_VK_MAP = {
    "shift": VK_SHIFT, "shft": VK_SHIFT,
    "ctrl": VK_CONTROL, "control": VK_CONTROL,
    "alt": VK_ALT,
    "win": VK_LWIN, "windows": VK_LWIN,
}


def simulate_hotkey(hotkey_str: str, hold_sec: float = 0.05):
    """Parse and simulate a hotkey string like 'ctrl+c', 'shift+y', 'enter', 'y'."""
    parts = hotkey_str.strip().split("+")
    mods = []
    for p in parts[:-1]:
        p = p.strip().lower()
        vk = _MOD_VK_MAP.get(p, 0)
        if vk:
            mods.append(vk)
    key = parts[-1].strip()
    vk = _vk_code(key)
    if vk == 0:
        return
    for mv in mods:
        _send_key(mv, key_up=False)
    _press_key(vk, hold_sec=hold_sec)
    for mv in reversed(mods):
        _send_key(mv, key_up=True)


# ---------------------------------------------------------------------------
# Clipboard helpers — Win32 API, no Tkinter dependency.
# Persistent message-only windows per thread: Windows empties the clipboard
# when the owning window is destroyed, so these must outlive any Set operation.
# ---------------------------------------------------------------------------
_clip_windows = {}


def _get_clipboard_window():
    """Return a message-only window owned by the calling thread."""
    tid = threading.get_ident()
    if tid not in _clip_windows:
        module = _kernel32.GetModuleHandleW(None)
        hwnd = _user32.CreateWindowExW(
            0, "Static", "", 0,
            0, 0, 0, 0,
            ctypes.wintypes.HWND(-3),  # HWND_MESSAGE
            0, module, 0,
        )
        _clip_windows[tid] = hwnd
    return _clip_windows[tid]


def clipboard_set(text: str):
    """Set text to Windows clipboard via Win32 API. Works from any thread."""
    _debug_log(f"clipboard_set: text={text!r}, len={len(text)}")
    hwnd = _get_clipboard_window()
    _debug_log(f"clipboard_set: hwnd={hwnd}")

    for i in range(5):
        if _user32.OpenClipboard(hwnd):
            _debug_log(f"clipboard_set: OpenClipboard OK (attempt {i+1})")
            break
        time.sleep(0.05)
    else:
        _debug_log("clipboard_set: OpenClipboard FAILED after 5 attempts")
        return

    ok = _user32.EmptyClipboard()
    _debug_log(f"clipboard_set: EmptyClipboard returned {ok}")

    hmem = _kernel32.GlobalAlloc(2, (len(text) + 1) * 2)  # GMEM_MOVEABLE
    _debug_log(f"clipboard_set: GlobalAlloc returned {hmem}")
    if hmem:
        pwsz = _kernel32.GlobalLock(hmem)
        _debug_log(f"clipboard_set: GlobalLock returned {pwsz}")
        if pwsz:
            buf = (ctypes.c_wchar * (len(text) + 1)).from_address(pwsz)
            buf.value = text
            _kernel32.GlobalUnlock(hmem)
            result = _user32.SetClipboardData(13, hmem)  # CF_UNICODETEXT
            _debug_log(f"clipboard_set: SetClipboardData returned {result}")
        else:
            _debug_log("clipboard_set: GlobalLock FAILED")
    else:
        _debug_log("clipboard_set: GlobalAlloc FAILED")

    _user32.CloseClipboard()
    _debug_log("clipboard_set: CloseClipboard done")


def clipboard_get() -> str:
    """Get text from Windows clipboard via Win32 API."""
    hwnd = _get_clipboard_window()

    for _ in range(5):
        if _user32.OpenClipboard(hwnd):
            break
        time.sleep(0.05)
    else:
        return ""

    try:
        handle = _user32.GetClipboardData(13)  # CF_UNICODETEXT
        if handle:
            pwsz = _kernel32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(pwsz)
            finally:
                _kernel32.GlobalUnlock(handle)
    finally:
        _user32.CloseClipboard()
    return ""


# ---------------------------------------------------------------------------
# Send sequence
# ---------------------------------------------------------------------------

def send_chat_message(text: str, hotkey: str) -> str | None:
    """Simulate keyboard to send a chat message in game.

    Sequence:
      1. Press hotkey to open game chat, wait 0.3s
      2. Set clipboard via Win32 API
      3. Ctrl+V to paste, wait 0.3s
      4. Enter to send
    """
    try:
        _debug_log(f"send_chat_message: text={text!r}, hotkey={hotkey!r}")
        hk = _vk_code(hotkey)
        if hk == 0:
            _debug_log(f"send_chat_message: invalid hotkey {hotkey!r}")
            return f"无效的按键: {hotkey}"

        _debug_log("send_chat_message: pressing hotkey")
        _press_key(hk)
        time.sleep(0.3)

        _debug_log("send_chat_message: calling clipboard_set")
        clipboard_set(text)
        _debug_log("send_chat_message: clipboard_set done")

        _combo([VK_CONTROL, VK_V])
        time.sleep(0.3)

        _press_key(VK_RETURN)
        time.sleep(0.3)

        _debug_log("send_chat_message: sequence complete, returning None")
        return None
    except Exception as e:
        _debug_log(f"send_chat_message EXCEPTION: {e}")
        return f"发送异常: {e}"


def run_send_sequence(text: str, hotkey: str):
    """Wrapper that runs the send sequence in a background thread."""
    _debug_log(f"run_send_sequence: spawning thread, text={text!r}, hotkey={hotkey!r}")
    def _run():
        err = send_chat_message(text, hotkey)
        if err:
            _debug_log(f"send_chat_message returned error: {err}")
    threading.Thread(target=_run, daemon=True).start()
