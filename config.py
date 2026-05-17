"""
Configuration management for ETS2 Chat Translator.
Reads/writes JSON config in Documents/ETS2 Translator/config.json
Documents path is obtained from Windows registry (same method as the reference DLL).
"""
import json
import os
import tempfile
import winreg
from dataclasses import dataclass, asdict

VERSION = "v1.0.2"


def get_documents_path():
    """Get the user's Documents folder from Windows registry.

    Same approach as the reference DLL: reads the 'Personal' value from
    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders.
    Falls back to USERPROFILE\\Documents if registry lookup fails.
    """
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        )
        path, _ = winreg.QueryValueEx(key, "Personal")
        winreg.CloseKey(key)
        if path:
            # Expand any environment variables (e.g., %USERPROFILE%)
            path = os.path.expandvars(path)
            path = os.path.normpath(path)
            if os.path.isdir(path):
                return path
    except (OSError, FileNotFoundError):
        pass

    # Fallback
    return os.path.join(os.environ.get("USERPROFILE", os.environ.get("HOMEDRIVE", "C:") + os.environ.get("HOMEPATH", "")), "Documents")


DOCUMENTS_PATH = get_documents_path()
CONFIG_DIR = os.path.join(DOCUMENTS_PATH, "ETS2 Translator")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_SYSTEM_PROMPT = (
    "You translate ETS2/TruckersMP in-game chat into natural Simplified Chinese. RULES:\n"
    "(1) Output ONLY the translated text. No quotes, no explanations, no pinyin, no language tags.\n"
    "(2) Expand common chat slang and abbreviations before translating:\n"
    "    u=you, r=are, ur=your, y=why, n=and, k/kk/ok=好的, thx/ty=thanks, np=no problem,\n"
    "    lol/lmao=哈哈, btw=by the way, brb=be right back, afk=away from keyboard, gg=good game,\n"
    "    gl=good luck, hf=have fun, hru=how are you, idk=i don't know, imo=in my opinion,\n"
    "    ttyl=talk to you later, wtf=what the heck, omg=oh my god, pls/plz=please, sry=sorry,\n"
    "    ez=easy, gj=good job, gn=good night, hi/hey=嗨, bro=兄弟, mate=伙计.\n"
    "(3) Translate text in ANY source language (German, Polish, Russian, Spanish, French, etc.)\n"
    "    into Chinese; for mixed-language input, translate every meaningful word.\n"
    "(4) Keep player names, place names that lack a common Chinese form, and number/units\n"
    "    (e.g., km/h) as-is.\n"
    "(5) If the entire input is already Chinese, return it unchanged."
)



@dataclass
class AppConfig:
    api_endpoint: str = ""
    api_key: str = ""
    api_model: str = ""
    target_language: str = "zh-CN"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    window_opacity: float = 0.80
    font_size: int = 12
    max_messages: int = 50
    player_name: str = ""  # auto-detected or manually set in-game name
    window_mode: str = "standalone"  # "standalone" or "overlay"
    click_through: bool = False  # only in overlay mode
    win_x: int = -1  # saved window x, -1 means auto-center
    win_y: int = -1  # saved window y
    win_w: int = 620  # saved window width
    win_h: int = 360  # saved window height
    chat_hotkey: str = "y"      # hotkey to open in-game chat window
    copy_hotkey: str = "ctrl+c"  # hotkey to copy translated text to clipboard
    paste_hotkey: str = "ctrl+v" # hotkey to paste (Ctrl+V) into game
    enter_hotkey: str = "enter"  # hotkey to press Enter in game
    send_hotkey: str = "shift+y" # global hotkey to focus translator input


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    ensure_config_dir()
    if not os.path.exists(CONFIG_PATH):
        cfg = AppConfig()
        save_config(cfg)
        return cfg

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    defaults = asdict(AppConfig())
    # Merge loaded data over defaults (allow partial configs)
    merged = {**defaults, **data}
    cfg = AppConfig(**{k: merged[k] for k in defaults})
    return cfg


def save_config(cfg: AppConfig):
    ensure_config_dir()
    content = json.dumps(asdict(cfg), indent=2, ensure_ascii=False)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            f.write(content)
    except PermissionError:
        _atomic_save(content)


def _atomic_save(content: str):
    fd = -1
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, prefix="config_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        fd = -1
        os.replace(tmp_path, CONFIG_PATH)
    except OSError:
        _fallback_save(content)
    finally:
        if fd != -1:
            try:
                os.close(fd)
            except OSError:
                pass
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _fallback_save(content: str):
    alt_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.environ["USERPROFILE"]), "ETS2 Translator")
    os.makedirs(alt_dir, exist_ok=True)
    alt_path = os.path.join(alt_dir, "config.json")
    with open(alt_path, "w", encoding="utf-8") as f:
        f.write(content)
