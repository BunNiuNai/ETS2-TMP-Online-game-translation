"""
TruckersMP chat log watcher.
Monitors Documents/ETS2MP/logs/chat_<date>_log.txt for new messages.
Documents path is obtained from Windows registry (same as the reference DLL).
"""
import glob
import os
import re
import threading
import time
from dataclasses import dataclass
from queue import Queue

from config import get_documents_path

DOCUMENTS_PATH = get_documents_path()
CHAT_LOG_DIR = os.path.join(DOCUMENTS_PATH, "ETS2MP", "logs")

# Log file naming since TruckersMP v0.2.3.7.2 (June 2022):
#   chat_YYYY_MM_DD_log.txt   e.g. chat_2026_05_16_log.txt
LOG_GLOB = "chat_*_log.txt"

# Hex timestamp variant used in some TMP versions:
#   chat_YYYY_MM_DD_log_<hex>.txt
LOG_GLOB_HEX = "chat_*_log_*.txt"

# Actual TruckersMP log format:
#   [Channel] [HH:MM:SS] PlayerName (ServerLetter TMP_ID): Message
# Examples:
#   [Global] [05:05:25] BoJo2k26 (1713): back :D
#   [Global] [21:18:55] TMP-Yunee. (A 158): hello
CHAT_LINE_RE = re.compile(
    r"^\[(?P<channel>.+?)\]\s+"
    r"\[(?P<time>\d{2}:\d{2}:\d{2})\]\s+"
    r"(?P<player>.+?)\s+\([A-Z]?\s*\d+\):\s+"
    r"(?P<text>.+)$"
)

_CJK_RE = re.compile(r"[一-鿿]")
_ALPHA_RE = re.compile(r"[a-zA-Z]")


def _is_chinese(text: str) -> bool:
    cjk = len(_CJK_RE.findall(text))
    alpha = len(_ALPHA_RE.findall(text))
    return cjk > alpha and cjk > len(text) * 0.3


@dataclass
class ChatMessage:
    timestamp: str
    player_name: str
    text: str
    is_self: bool = False


def find_latest_log():
    """Find the most recent chat log file in the logs directory."""
    if not os.path.isdir(CHAT_LOG_DIR):
        return None

    # Primary pattern: chat_YYYY_MM_DD_log.txt
    pattern = os.path.join(CHAT_LOG_DIR, LOG_GLOB)
    files = glob.glob(pattern)

    # Secondary pattern: chat_YYYY_MM_DD_log_<hex>.txt
    if not files:
        pattern2 = os.path.join(CHAT_LOG_DIR, LOG_GLOB_HEX)
        files = glob.glob(pattern2)

    # Fallback: any chat_*.txt
    if not files:
        pattern3 = os.path.join(CHAT_LOG_DIR, "chat_*.txt")
        files = glob.glob(pattern3)

    if files:
        files.sort(key=os.path.getmtime, reverse=True)
        return files[0]
    return None


def parse_line(line: str, self_name: str | None = None) -> ChatMessage | None:
    """Parse a chat log line into a ChatMessage, or None if not a player chat line.

    Matches: [Channel] [HH:MM:SS] PlayerName (ServerLetter ID): Message
    System messages (no player name / TMP ID) are skipped.
    When self_name is provided, messages from that player get is_self=True.
    """
    m = CHAT_LINE_RE.match(line.strip())
    if not m:
        return None
    player = m.group("player")
    is_self = self_name is not None and player == self_name
    return ChatMessage(
        timestamp=m.group("time"),
        player_name=player,
        text=m.group("text"),
        is_self=is_self,
    )


def log_dir_status():
    """Return a diagnostic string describing the state of the chat log directory."""
    if not os.path.isdir(CHAT_LOG_DIR):
        return f"目录不存在: {CHAT_LOG_DIR}"
    files = sorted(glob.glob(os.path.join(CHAT_LOG_DIR, "chat_*")),
                   key=os.path.getmtime, reverse=True)
    if not files:
        return f"目录存在但无聊天日志文件: {CHAT_LOG_DIR}"
    latest = files[0]
    size = os.path.getsize(latest)
    mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(latest)))
    return f"最新日志: {os.path.basename(latest)} ({size} bytes, 修改于 {mtime})"


class ChatMonitor(threading.Thread):
    """Background thread that tails the TruckersMP chat log."""

    def __init__(self, message_queue: Queue, self_name_ref: dict):
        super().__init__(daemon=True)
        self.queue = message_queue
        self._self_name_ref = self_name_ref  # mutable ref: {"name": str}
        self._stop_event = threading.Event()
        self._log_path = None
        self._last_size = 0
        self.status = "未启动"

    @property
    def _self_name(self) -> str | None:
        name = self._self_name_ref.get("name", "")
        return name if name else None

    def run(self):
        self.status = "运行中"
        while not self._stop_event.is_set():
            if self._log_path is None or not os.path.exists(self._log_path):
                self._log_path = find_latest_log()
                if self._log_path:
                    self._last_size = os.path.getsize(self._log_path)
                    self.status = f"已找到日志: {os.path.basename(self._log_path)}"
                else:
                    self.status = log_dir_status()

            if self._log_path and os.path.exists(self._log_path):
                self._tail_once()

            self._stop_event.wait(0.5)

    def _tail_once(self):
        try:
            current_size = os.path.getsize(self._log_path)
            if current_size < self._last_size:
                self._last_size = 0

            if current_size <= self._last_size:
                return

            with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._last_size)
                new_data = f.read(current_size - self._last_size)
                self._last_size = current_size

            for line in new_data.splitlines():
                self_name = self._self_name
                msg = parse_line(line, self_name)
                if msg is None:
                    continue
                # Auto-detect self: first player who sends Chinese messages
                if not self_name and _is_chinese(msg.text):
                    self._self_name_ref["name"] = msg.player_name
                    msg.is_self = True
                self.queue.put(msg)
        except OSError:
            pass

    def stop(self):
        self.status = "已停止"
        self._stop_event.set()
