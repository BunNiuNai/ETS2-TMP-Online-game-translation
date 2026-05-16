"""
LLM translation client - OpenAI-compatible API (/v1/chat/completions).
Batch mode: collects messages within a short window, sends them as one request.
LRU cache: avoids re-translating identical strings.
"""
import json
import re
import threading
import time
from collections import OrderedDict
from queue import Queue

import httpx

from config import AppConfig

_CJK_RE = re.compile(r"[一-鿿]")
_ALPHA_RE = re.compile(r"[a-zA-Z]")

CACHE_SIZE = 200
BATCH_WINDOW = 0.8  # seconds to wait for more messages before sending batch
BATCH_SEPARATOR = "\n---\n"


class LRUCache:
    def __init__(self, maxsize: int = CACHE_SIZE):
        self.maxsize = maxsize
        self._cache = OrderedDict()

    def get(self, key: str) -> str | None:
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: str):
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = value
        while len(self._cache) > self.maxsize:
            self._cache.popitem(last=False)


class Translator(threading.Thread):
    """Background worker: batches messages, translates via LLM API, caches results."""

    def __init__(self, cfg: AppConfig, in_queue: Queue, out_queue: Queue):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.in_queue = in_queue
        self.out_queue = out_queue
        self._stop_event = threading.Event()
        self._cache = LRUCache(CACHE_SIZE)
        self._client = httpx.Client(timeout=30.0)
        self.stats = {"translated": 0, "cached": 0, "self": 0}

    def run(self):
        batch = []
        batch_deadline = None

        while not self._stop_event.is_set():
            try:
                timeout = 0.3
                if batch and batch_deadline:
                    remaining = batch_deadline - time.monotonic()
                    timeout = max(0, min(0.3, remaining))
                msg = self.in_queue.get(timeout=timeout)
            except Exception:
                # Timeout — flush batch if deadline passed
                if batch and time.monotonic() >= batch_deadline:
                    self._flush(batch)
                    batch = []
                    batch_deadline = None
                continue

            if msg is None:
                if batch:
                    self._flush(batch)
                break

            # Skip own messages (already Chinese)
            if msg.is_self:
                self.stats["self"] += 1
                self.out_queue.put((msg, msg.text))
                continue

            # Check cache
            cached = self._cache.get(msg.text)
            if cached is not None:
                self.stats["cached"] += 1
                self.out_queue.put((msg, cached))
                continue

            # Add to batch
            batch.append(msg)
            if batch_deadline is None:
                batch_deadline = time.monotonic() + BATCH_WINDOW

            # Flush if batch is large enough
            if len(batch) >= 8:
                self._flush(batch)
                batch = []
                batch_deadline = None

    def _flush(self, batch):
        if not batch:
            return
        self.stats["translated"] += len(batch)
        try:
            if len(batch) == 1:
                text = batch[0].text
                translated = self._call_api(text)
                self._cache.put(text, translated)
                self.out_queue.put((batch[0], translated))
            else:
                combined = BATCH_SEPARATOR.join(m.text for m in batch)
                result = self._call_api(combined)
                parts = [p.strip() for p in result.split(BATCH_SEPARATOR)]
                for i, msg in enumerate(batch):
                    trans = parts[i] if i < len(parts) else msg.text
                    self._cache.put(msg.text, trans)
                    self.out_queue.put((msg, trans))
        except Exception as e:
            err_msg = self._format_error(e)
            for msg in batch:
                self.out_queue.put((msg, err_msg))

    def _call_api(self, text: str) -> str:
        if self._should_skip(text):
            return text

        payload = {
            "model": self.cfg.api_model,
            "messages": [
                {"role": "system", "content": self.cfg.system_prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0.2,
            "max_tokens": 500 if BATCH_SEPARATOR not in text else 500 * text.count(BATCH_SEPARATOR) + 500,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.cfg.api_key}",
        }

        resp = self._client.post(self.cfg.api_endpoint, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

    def _should_skip(self, text: str) -> bool:
        if self.cfg.target_language == "zh-CN":
            cjk = len(_CJK_RE.findall(text))
            alpha = len(_ALPHA_RE.findall(text))
            if cjk > alpha and cjk > len(text) * 0.3:
                return True
        return False

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, httpx.ConnectError):
            return "[网络错误] 无法连接到 API 服务器，请检查地址和网络"
        if isinstance(exc, httpx.TimeoutException):
            return "[请求超时] API 服务器响应超时，请稍后重试"
        if isinstance(exc, httpx.HTTPStatusError):
            code = exc.response.status_code
            if code == 401:
                return "[认证失败] API 密钥无效，请检查设置"
            if code == 403:
                return "[权限不足] 无权访问该 API，请检查密钥权限"
            if code == 429:
                return "[请求过于频繁] 请稍后重试"
            if code in (500, 502, 503):
                return f"[服务器错误 {code}] API 服务器异常，请稍后重试"
            return f"[HTTP 错误 {code}] {exc.response.reason_phrase}"
        if isinstance(exc, (KeyError, IndexError)):
            return "[响应格式错误] API 返回了意外的数据结构"
        if isinstance(exc, json.JSONDecodeError):
            return "[响应格式错误] API 返回了无效的 JSON"
        return f"[翻译失败] {exc}"

    def stop(self):
        self._stop_event.set()
        self._client.close()


def test_connection(endpoint: str, api_key: str, model: str) -> tuple:
    """Test API connectivity with a minimal request. Returns (success: bool, message: str)."""
    endpoint = endpoint.strip()
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = "https://" + endpoint

    try:
        client = httpx.Client(timeout=15.0)
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Hi"},
            ],
            "max_tokens": 5,
            "temperature": 0,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        resp = client.post(endpoint, json=payload, headers=headers)
        client.close()
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        return True, f"连通成功 — {content[:60]}"
    except httpx.ConnectError:
        return False, "无法连接到 API 服务器，请检查地址和网络"
    except httpx.TimeoutException:
        return False, "连接超时，请检查网络或 API 地址是否可访问"
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        detail = _parse_api_error(e.response)
        if code == 401:
            return False, f"API Key 无效 (401){detail}"
        if code == 403:
            return False, f"无权访问 (403){detail}"
        if code == 404:
            return False, f"未找到 (404){detail}\n请检查 API 地址路径和模型名称"
        if code == 429:
            return False, "请求过于频繁 (429)，请稍后重试"
        return False, f"HTTP 错误 {code}{detail}"
    except (KeyError, IndexError):
        return False, "API 响应格式异常，请确认 API 地址指向 chat/completions 端点"
    except json.JSONDecodeError:
        return False, "API 返回了无效的 JSON，请确认 API 地址正确"
    except Exception as e:
        return False, f"连接失败: {e}"


SEND_SYSTEM_PROMPT = (
    "You are a Chinese-to-English translator for in-game chat. RULES:\n"
    "(1) Output ONLY the English translation. No quotes, no explanations.\n"
    "(2) Use natural, casual gamer English. Prefer short forms where natural.\n"
    "(3) Keep player names, place names, and numbers as-is.\n"
    "(4) If the input is already English, return it unchanged."
)


def translate_to_english(cfg: AppConfig, text: str) -> str:
    """Translate Chinese text to English for sending in chat.
    Returns the translated text, or raises an exception on error."""
    endpoint = cfg.api_endpoint.strip()
    if not endpoint.startswith(("http://", "https://")):
        endpoint = "https://" + endpoint

    payload = {
        "model": cfg.api_model,
        "messages": [
            {"role": "system", "content": SEND_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.2,
        "max_tokens": 300,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }
    # Use httpx.post() directly — simpler than Client context manager,
    # handles connection pooling and timeout internally.
    resp = httpx.post(endpoint, json=payload, headers=headers, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _parse_api_error(response) -> str:
    try:
        body = response.json()
        err = body.get("error", {})
        msg = err.get("message", "") if isinstance(err, dict) else str(err)
        if msg:
            return f" — {msg}"
    except Exception:
        pass
    return ""
