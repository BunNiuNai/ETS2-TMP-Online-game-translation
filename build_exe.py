"""
Build standalone .exe using PyInstaller.
Usage: python build_exe.py
Output: dist/ETS2_Chat_Translator.exe
"""
import subprocess
import sys
import os

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(PROJECT_DIR, "main.py")
NAME = "ETS2_Chat_Translator"
ICON = os.path.join(PROJECT_DIR, "icon.ico")
ICON_SRC = os.path.join(PROJECT_DIR, "xintubiao.png")


def build():
    # Convert PNG icon to ICO if needed
    if os.path.exists(ICON_SRC):
        _convert_icon()
    elif not os.path.exists(ICON):
        _generate_icon()

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name", NAME,
        "--add-data", f"{ICON};.",
        "--hidden-import", "httpx",
        "--clean",
        MAIN,
    ]

    print(f"[*] Building {NAME}.exe ...")
    subprocess.check_call(cmd)
    print(f"[*] Done: {os.path.join(PROJECT_DIR, 'dist', NAME + '.exe')}")


def _convert_icon():
    """Convert xintubiao.png to icon.ico for PyInstaller."""
    try:
        from PIL import Image
        img = Image.open(ICON_SRC)
        # Resize to standard icon sizes
        sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
        img.save(ICON, format="ICO", sizes=sizes)
        print(f"[*] Converted {ICON_SRC} -> {ICON}")
    except Exception as e:
        print(f"[!] Could not convert icon: {e}")
        # Fallback: try to use PNG directly (PyInstaller may handle it)
        import shutil
        shutil.copy(ICON_SRC, ICON)


def _generate_icon():
    """Generate a simple .ico file using Pillow (fallback)."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (30, 30, 30, 255))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(86, 156, 214, 255))
        draw.text((16, 14), "T", fill="white")
        img.save(ICON, format="ICO")
        print(f"[*] Generated icon: {ICON}")
    except Exception as e:
        print(f"[!] Could not generate icon: {e}")


if __name__ == "__main__":
    build()
