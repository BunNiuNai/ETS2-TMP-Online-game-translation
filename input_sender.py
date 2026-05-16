"""
Keyboard simulation and send sequence for in-game chat.
Uses Win32 SendInput API for reliable key injection.
"""
import ctypes
import ctypes.wintypes
import time
import threading

# Desktop window handle used as clipboard owner. OpenClipboard(NULL) combined
# with EmptyClipboard() causes the clipboard owner to be NULL, which makes
# SetClipboardData fail silently. Using GetDesktopWindow() provides a valid HWND.
_GetDesktopWindow = ctypes.windll.user32.GetDesktopWindow
_GetDesktopWindow.restype = ctypes.wintypes.HWND
_CLIP_HWND = _GetDesktopWindow()


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


def _clipboard_set(text: str):
    """Set text to Windows clipboard. Retries if OpenClipboard fails."""
    for _ in range(5):
        if ctypes.windll.user32.OpenClipboard(_CLIP_HWND):
            break
        time.sleep(0.05)
    else:
        print("[SendError] OpenClipboard failed for set")
        return
    ctypes.windll.user32.EmptyClipboard()
    # GMEM_MOVEABLE = 2
    hmem = ctypes.windll.kernel32.GlobalAlloc(2, (len(text) + 1) * 2)
    if hmem:
        pwsz = ctypes.windll.kernel32.GlobalLock(hmem)
        buf = (ctypes.c_wchar * (len(text) + 1)).from_address(pwsz)
        buf.value = text
        ctypes.windll.kernel32.GlobalUnlock(hmem)
        ctypes.windll.user32.SetClipboardData(13, hmem)  # CF_UNICODETEXT = 13
    ctypes.windll.user32.CloseClipboard()


def _clipboard_get() -> str:
    """Get text from Windows clipboard. Retries if OpenClipboard fails."""
    for _ in range(5):
        if ctypes.windll.user32.OpenClipboard(_CLIP_HWND):
            break
        time.sleep(0.05)
    else:
        print("[SendError] OpenClipboard failed for get")
        return ""
    try:
        handle = ctypes.windll.user32.GetClipboardData(13)  # CF_UNICODETEXT
        if handle:
            pwsz = ctypes.windll.kernel32.GlobalLock(handle)
            try:
                return ctypes.wstring_at(pwsz)
            finally:
                ctypes.windll.kernel32.GlobalUnlock(handle)
    finally:
        ctypes.windll.user32.CloseClipboard()
    return ""


def send_chat_message(text: str, hotkey: str) -> str | None:
    """
    Simulate keyboard input to send a chat message in game.

    Sequence:
      1. Press hotkey to open game chat, wait 0.5s
      2. Press hotkey again, wait 0.5s
      3. Ctrl+V to paste, wait 0.2s
      4. Enter to send

    Clipboard is set by caller on main thread before the countdown.
    Returns None on success, or an error message string on failure.
    """
    try:
        hk = _vk_code(hotkey)
        if hk == 0:
            return f"无效的按键: {hotkey}"

        # Press hotkey to open chat (first press)
        _press_key(hk)
        time.sleep(0.5)

        # Press hotkey again (second press ensures chat input is focused)
        _press_key(hk)
        time.sleep(0.5)

        # Paste (Ctrl+V)
        _combo([VK_CONTROL, VK_V])
        time.sleep(0.2)

        # Send (Enter)
        _press_key(VK_RETURN)
        time.sleep(0.3)

        return None
    except Exception as e:
        return f"发送异常: {e}"


def run_send_sequence(text: str, hotkey: str):
    """Wrapper that runs the send sequence in a thread."""
    def _run():
        err = send_chat_message(text, hotkey)
        if err:
            print(f"[SendError] {err}")
    threading.Thread(target=_run, daemon=True).start()
