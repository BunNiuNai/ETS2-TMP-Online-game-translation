"""
Auto-update: checks GitHub Releases, downloads new exe, replaces via batch script.
"""
import os
import sys
import tempfile
import threading
from urllib.request import urlopen, urlretrieve
from urllib.error import URLError
import json

from config import VERSION

GITHUB_API = "https://api.github.com/repos/BunNiuNai/ets2-translator/releases/latest"


def check_for_update():
    """Query GitHub latest release. Returns (has_update, version, download_url) or (False, "", "")."""
    try:
        req = urlopen(GITHUB_API, timeout=10)
        data = json.loads(req.read().decode())
        latest = data.get("tag_name", "")
        if not latest:
            return False, "", ""

        if _version_newer(latest, VERSION):
            url = ""
            for asset in data.get("assets", []):
                if asset.get("name", "").endswith(".exe"):
                    url = asset.get("browser_download_url", "")
                    break
            return True, latest, url
        return False, latest, ""
    except (URLError, OSError, json.JSONDecodeError, KeyError):
        return False, "", ""


def _version_newer(latest: str, current: str) -> bool:
    """Compare 'v1.0.8' > 'v1.0.7'."""
    def parse(v):
        v = v.strip().lstrip("v")
        parts = v.split(".")
        return tuple(int(p) for p in parts if p.isdigit())
    try:
        return parse(latest) > parse(current)
    except (ValueError, IndexError):
        return False


def download_update(url: str, progress_cb=None) -> str | None:
    """Download new exe to a temp path. Returns path on success, None on failure.
    progress_cb(percent: int) is called during download.
    """
    try:
        tmp = tempfile.mktemp(suffix=".exe", prefix="ets2_update_")
        _download_with_progress(url, tmp, progress_cb)
        return tmp
    except (URLError, OSError) as e:
        if progress_cb:
            progress_cb(-1)
        return None


def _download_with_progress(url: str, dest: str, progress_cb=None):
    """Download file with progress callback."""
    import ctypes
    resp = urlopen(url, timeout=60)
    total = int(resp.headers.get("Content-Length", 0))
    downloaded = 0
    block_size = 8192

    with open(dest, "wb") as f:
        while True:
            chunk = resp.read(block_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb and total > 0:
                progress_cb(int(downloaded * 100 / total))

    if total > 0 and downloaded < total * 0.95:
        raise OSError("Download incomplete")


def apply_update(new_exe_path: str, own_exe_path: str):
    """Create and launch a batch script that replaces the running exe after exit.
    Called right before sys.exit()."""
    bat = os.path.join(tempfile.gettempdir(), "ets2_update.bat")

    with open(bat, "w", encoding="ascii") as f:
        f.write("@echo off\r\n")
        f.write(":loop\r\n")
        f.write(f'tasklist /fi "PID eq {os.getpid()}" 2>nul | find "{os.getpid()}" >nul\r\n')
        f.write("if not errorlevel 1 (\r\n")
        f.write("    ping 127.0.0.1 -n 2 >nul\r\n")
        f.write("    goto loop\r\n")
        f.write(")\r\n")
        f.write(f'move /Y "{new_exe_path}" "{own_exe_path}"\r\n')
        f.write(f'start "" "{own_exe_path}"\r\n')
        f.write(f'del "{bat}"\r\n')

    # Launch batch detached
    ctypes.windll.shell32.ShellExecuteW(None, "open", bat, None, None, 0)
