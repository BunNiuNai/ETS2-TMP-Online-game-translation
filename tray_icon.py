"""
Minimal system tray icon using pure ctypes + Win32 API.
Avoids pystray which is incompatible with Python 3.14 free-threading.
"""
import ctypes
import threading
from ctypes import wintypes

# Win32 API bindings
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# Set argtypes/restype for critical functions to avoid ctypes conversion errors on 64-bit
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL

# Constants
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 1
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202
WM_COMMAND = 0x0111
NIM_ADD = 0
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004
NIF_STATE = 0x00000008
NIS_HIDDEN = 0x00000001
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x0010
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
MF_STRING = 0x00000000
MF_SEPARATOR = 0x00000800
MF_CHECKED = 0x00000008
MF_UNCHECKED = 0x00000000
MF_DEFAULT = 0x00001000
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
CW_USEDEFAULT = 0x80000000
WS_OVERLAPPED = 0x00000000
COLOR_WINDOW = 5
IDI_APPLICATION = 32512
BS_PATTERN = 3
HS_VERTICAL = 1

class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", wintypes.BYTE * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


def _create_icon():
    """Create a 32x32 icon programmatically using GDI (no PIL dependency)."""
    # Create a bitmap and draw on it
    hdc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(hdc)
    bm = gdi32.CreateCompatibleBitmap(hdc, 32, 32)
    old_bm = gdi32.SelectObject(mem_dc, bm)

    # Background fill (#1e1e1e)
    bg_brush = gdi32.CreateSolidBrush(0x1e1e1e)
    rect = wintypes.RECT(0, 0, 32, 32)
    ctypes.windll.user32.FillRect(mem_dc, ctypes.byref(rect), bg_brush)
    gdi32.DeleteObject(bg_brush)

    # Inner square (#569cd6)
    inner_brush = gdi32.CreateSolidBrush(0xd69c56)  # BGR = 0xd69c56
    inner_rect = wintypes.RECT(4, 4, 28, 28)
    ctypes.windll.user32.FillRect(mem_dc, ctypes.byref(inner_rect), inner_brush)
    gdi32.DeleteObject(inner_brush)

    # Text "T" in white
    gdi32.SetBkMode(mem_dc, 1)  # TRANSPARENT
    gdi32.SetTextColor(mem_dc, 0xFFFFFF)
    font = gdi32.CreateFontW(
        16, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0,
        "Microsoft YaHei"
    )
    old_font = gdi32.SelectObject(mem_dc, font)
    text_rect = wintypes.RECT(0, 6, 32, 32)
    ctypes.windll.user32.DrawTextW(mem_dc, "T", 1, ctypes.byref(text_rect), 0x0001 | 0x0100)

    gdi32.SelectObject(mem_dc, old_font)
    gdi32.DeleteObject(font)

    # Create icon from bitmap
    bm_info = ctypes.create_string_buffer(84)  # BITMAPINFOHEADER(40) + masks(4*3=12) + color table = 56 is enough, use 84 for safety
    # BITMAPINFOHEADER
    ctypes.memmove(bm_info, b"\x28\x00\x00\x00", 4)  # biSize
    ctypes.memmove(ctypes.addressof(bm_info) + 4, b"\x20\x00\x00\x00", 4)  # biWidth = 32
    ctypes.memmove(ctypes.addressof(bm_info) + 8, b"\x40\x00\x00\x00", 4)  # biHeight = 64 (top-down DIB with double height for mask)
    ctypes.memmove(ctypes.addressof(bm_info) + 12, b"\x01\x00", 2)  # biPlanes = 1
    ctypes.memmove(ctypes.addressof(bm_info) + 14, b"\x20\x00", 2)  # biBitCount = 32

    # Get bitmap bits
    buf_size = 32 * 32 * 4
    bits = ctypes.create_string_buffer(buf_size)
    gdi32.GetBitmapBits(bm, buf_size, bits)

    # Create XOR mask (top half) and AND mask (bottom half) for the icon
    # For 32-bit: XOR mask is the color data, AND mask is all zeros
    xor_mask = ctypes.create_string_buffer(buf_size)
    ctypes.memmove(xor_mask, bits, buf_size)
    and_mask = ctypes.create_string_buffer(32 * 4)  # 1 bit per pixel, 4 bytes per row
    ctypes.memset(and_mask, 0, 32 * 4)

    hicon = user32.CreateIconIndirect(
        ctypes.c_bool(True),  # fIcon
        0, 0,  # xHotspot, yHotspot
        xor_mask,  # hbmMask (color)
        and_mask,  # hbmColor (mask)
    )

    # Actually CreateIconIndirect takes a pointer to ICONINFO
    # Let me use a different approach - just use LoadImage to create icon from bitmap data

    gdi32.SelectObject(mem_dc, old_bm)
    gdi32.DeleteObject(bm)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, hdc)

    return hicon


def _create_icon_simple():
    """Create a simple 32x32 icon with GDI - returns HICON."""
    hdc = user32.GetDC(0)
    mem_dc = gdi32.CreateCompatibleDC(hdc)

    # Create color bitmap (32x32, 32-bit)
    bm = gdi32.CreateCompatibleBitmap(hdc, 32, 32)
    old_bm = gdi32.SelectObject(mem_dc, bm)

    # Fill background
    bg = gdi32.CreateSolidBrush(0x1e1e1e)  # dark bg
    r = wintypes.RECT(0, 0, 32, 32)
    user32.FillRect(mem_dc, ctypes.byref(r), bg)
    gdi32.DeleteObject(bg)

    # Colored square
    inner = gdi32.CreateSolidBrush(0xd69c56)  # BGR #569cd6
    r2 = wintypes.RECT(4, 4, 28, 28)
    user32.FillRect(mem_dc, ctypes.byref(r2), inner)
    gdi32.DeleteObject(inner)

    # Text
    gdi32.SetBkMode(mem_dc, 1)
    gdi32.SetTextColor(mem_dc, 0xFFFFFF)
    font = gdi32.CreateFontW(18, 0, 0, 0, 700, 0, 0, 0, 0, 0, 0, 0, 0, "Microsoft YaHei")
    old_font = gdi32.SelectObject(mem_dc, font)
    tr = wintypes.RECT(0, 4, 32, 32)
    user32.DrawTextW(mem_dc, "T", 1, ctypes.byref(tr), 0x0001 | 0x0100)
    gdi32.SelectObject(mem_dc, old_font)
    gdi32.DeleteObject(font)

    # Get bitmap bits
    bmp_bits = (wintypes.BYTE * (32 * 32 * 4))()
    gdi32.GetBitmapBits(bm, ctypes.sizeof(bmp_bits), bmp_bits)

    # Create mask bitmap (1bpp, all white = all pixels visible)
    mask_dc = gdi32.CreateCompatibleDC(hdc)
    mask_bm = gdi32.CreateBitmap(32, 32, 1, 1, None)
    old_mask_bm = gdi32.SelectObject(mask_dc, mask_bm)
    # Fill with white (all bits = 1)
    white_brush = gdi32.CreateSolidBrush(0xFFFFFF)
    mask_r = wintypes.RECT(0, 0, 32, 32)
    user32.FillRect(mask_dc, ctypes.byref(mask_r), white_brush)
    gdi32.DeleteObject(white_brush)

    mask_bits = (wintypes.BYTE * (32 * 4))()
    gdi32.GetBitmapBits(mask_bm, ctypes.sizeof(mask_bits), mask_bits)

    # Create icon
    class ICONINFO(ctypes.Structure):
        _fields_ = [
            ("fIcon", wintypes.BOOL),
            ("xHotspot", wintypes.DWORD),
            ("yHotspot", wintypes.DWORD),
            ("hbmMask", wintypes.HBITMAP),
            ("hbmColor", wintypes.HBITMAP),
        ]

    ii = ICONINFO()
    ii.fIcon = True
    ii.xHotspot = 0
    ii.yHotspot = 0
    ii.hbmColor = bm
    ii.hbmMask = mask_bm

    hicon = user32.CreateIconIndirect(ctypes.byref(ii))

    # Cleanup
    gdi32.SelectObject(mask_dc, old_mask_bm)
    gdi32.DeleteObject(mask_bm)
    gdi32.DeleteDC(mask_dc)
    gdi32.SelectObject(mem_dc, old_bm)
    gdi32.DeleteObject(bm)
    gdi32.DeleteDC(mem_dc)
    user32.ReleaseDC(0, hdc)

    return hicon


class TrayIcon:
    """Minimal system tray icon using Win32 API directly."""

    def __init__(self, title: str = "ETS2 聊天翻译器"):
        self._title = title
        self._hwnd = None
        self._hicon = None
        self._thread = None
        self._running = False
        self._menu_items = []  # list of (id, label, callback, is_checked_fn)
        self._next_menu_id = 1000
        self._default_cb = None  # default action (double-click / left-click)

    def set_menu(self, items, default_cb=None):
        """Set the right-click menu.

        items: list of dicts or tuples:
            {"label": str, "callback": callable, "checked": callable|None}
            or ("---",) for separator
        default_cb: called on double-click or single left-click
        """
        self._menu_items = []
        self._next_menu_id = 1000
        for item in items:
            if isinstance(item, dict):
                mid = self._next_menu_id
                self._next_menu_id += 1
                self._menu_items.append({
                    "id": mid,
                    "label": item["label"],
                    "callback": item.get("callback"),
                    "checked_fn": item.get("checked"),
                    "default": item.get("default", False),
                })
            else:
                self._menu_items.append({"id": 0, "label": "---", "separator": True})
        self._default_cb = default_cb

    def start(self):
        """Create tray icon and start message pump in background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Remove tray icon and stop message pump."""
        self._running = False
        if self._hwnd:
            user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAYICON:
            if lparam == WM_RBUTTONUP:
                self._show_menu()
            elif lparam == WM_LBUTTONDBLCLK or lparam == WM_LBUTTONUP:
                if self._default_cb:
                    self._default_cb()
            return 0
        elif msg == WM_COMMAND:
            mid = wparam & 0xFFFF
            for item in self._menu_items:
                if item.get("id") == mid and item.get("callback"):
                    item["callback"]()
                    break
            return 0
        elif msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _message_loop(self):
        # Register window class
        wnd_proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )
        self._wnd_proc_ref = wnd_proc_type(self._wnd_proc)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT),
                ("style", wintypes.UINT),
                ("lpfnWndProc", wintypes.LPVOID),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HCURSOR),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON),
            ]

        hinst = kernel32.GetModuleHandleW(None)
        class_name = "ETS2TrayIconClass"

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(self._wnd_proc_ref, wintypes.LPVOID)
        wc.hInstance = hinst
        wc.lpszClassName = class_name
        wc.hbrBackground = wintypes.HBRUSH(COLOR_WINDOW + 1)

        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            return

        # Create hidden message-only window
        self._hwnd = user32.CreateWindowExW(
            0, class_name, "ETS2Tray",
            WS_OVERLAPPED,
            0, 0, 0, 0,
            0, 0, hinst, 0
        )

        if not self._hwnd:
            return

        # Create icon
        self._hicon = _create_icon_simple()

        # Add tray icon
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self._hicon or user32.LoadIconW(0, IDI_APPLICATION)
        nid.szTip = self._title

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        # Message loop
        msg = wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        # Remove tray icon
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))

        # Destroy icon
        if self._hicon:
            user32.DestroyIcon(self._hicon)
            self._hicon = None

        # Destroy window
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None

    def _show_menu(self):
        if not self._menu_items:
            return

        # Create popup menu
        menu = user32.CreatePopupMenu()

        for item in self._menu_items:
            if item.get("separator"):
                user32.AppendMenuW(menu, MF_SEPARATOR, 0, 0)
            else:
                flags = MF_STRING
                if item.get("default"):
                    flags |= MF_DEFAULT

                # Check if item should be checked
                if item.get("checked_fn"):
                    try:
                        is_checked = item["checked_fn"]()
                    except Exception:
                        is_checked = False
                    if is_checked:
                        flags |= MF_CHECKED

                user32.AppendMenuW(menu, flags, item["id"], item["label"])

        # Get cursor position
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))

        # Required: give the popup menu focus so it receives clicks
        user32.SetForegroundWindow(self._hwnd)

        # Track menu
        cmd = user32.TrackPopupMenu(
            menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
            pt.x, pt.y, 0, self._hwnd, 0
        )

        # Execute command
        if cmd:
            user32.PostMessageW(self._hwnd, WM_COMMAND, cmd, 0)

        user32.DestroyMenu(menu)

    def modify_tip(self, tip: str):
        """Update the tooltip text."""
        if not self._hwnd:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_TIP
        nid.szTip = tip
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))
