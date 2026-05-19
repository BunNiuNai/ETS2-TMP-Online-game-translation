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
    "You are a translator for ETS2/TruckersMP in-game chat. Translate Chinese into natural,\n"
    "accurate English that a real gamer would type. Never summarize, never omit, never add.\n"
    "\n"
    "=== ETS2 GAME TERMINOLOGY (Chinese → English) ===\n"
    "卡车 → truck    挂车/拖车 → trailer    货物/货 → cargo    任务/送货 → job/delivery\n"
    "车队 → convoy    路线 → route    目的地 → destination    车库 → garage\n"
    "休息区/停车场 → rest stop    加油站 → gas station    维修站 → repair shop\n"
    "渡轮 → ferry    隧道 → tunnel    收费站 → toll gate    桥 → bridge\n"
    "高速公路/高速 → highway    车道 → lane    限速 → speed limit\n"
    "警察 → cop/police    罚款 → fine/ticket    车灯 → headlights    发动机 → engine\n"
    "损坏 → damage/damaged    超车 → overtake    加油 → refuel/get fuel\n"
    "碰撞 → collision    无碰撞 → no collision    延迟/卡顿 → lag\n"
    "服务器 → server    管理员 → admin    模组 → mod    举报 → report\n"
    "封禁 → ban    踢出 → kick    掉线 → disconnect/dc    重连 → reconnect/rc\n"
    "存档 → save    读档 → load\n"
    "加来 → Calais    杜伊斯堡 → Duisburg    鹿特丹 → Rotterdam\n"
    "多佛 → Dover    希尔克内斯 → Kirkenes    斯堪的纳维亚 → Scandinavia\n"
    "\n"
    "=== GREETINGS & FAREWELLS ===\n"
    "嗨/你好/在吗 → hi/hey/yo     早上好 → good morning     晚安 → good night\n"
    "拜拜/回头见/再见/下了 → bye/cya/see you later     欢迎回来 → welcome back/wb\n"
    "好久不见 → long time no see     你好吗 → how are you/hru\n"
    "\n"
    "=== QUESTIONS & ANSWERS ===\n"
    "你是哪国人 → where are you from      你在哪 → where are you\n"
    "你在干嘛 → what are you doing       有人吗 → anyone here\n"
    "能听到我吗 → can you hear me       你会中文/英语吗 → do you speak Chinese/English\n"
    "多少钱 → how much      多久/多远 → how long      发生什么了 → what happened\n"
    "是的/对的/对/没错 → yeah/yep     不是/不对/没有 → nah/nope\n"
    "也许/可能 → maybe      当然 → of course/sure      真的吗 → really?/fr?\n"
    "不知道 → idk      我觉得 → imo/i think     说实话 → tbh\n"
    "\n"
    "=== REQUESTS & COMMANDS ===\n"
    "帮我/帮帮忙/救命 → help me / help      需要帮忙 → need help\n"
    "跟我走/跟着我 → follow me      加入我们 → join us      我能加入吗 → can I join\n"
    "等一下/稍等/等等 → wait / hold on / sec      快点/赶紧 → hurry / quick\n"
    "出发/走/冲/开始 → lets go / gogogo / come on      停下/停车 → stop / pull over\n"
    "慢点/慢一点 → slow down      快点/加速 → speed up      靠边/停路边 → pull over\n"
    "左转 → turn left   右转 → turn right   直走/直行 → go straight\n"
    "掉头/调头 → turn around / u-turn      倒车 → back up\n"
    "保持车道 → stay in this lane      变道 → change lane\n"
    "小心/当心/注意 → watch out / be careful / heads up\n"
    "\n"
    "=== ROAD & NAVIGATION ===\n"
    "堵车/塞车/拥堵 → traffic jam      事故/车祸/撞了 → accident/crash\n"
    "路被堵了/路封了 → road is blocked / road closed      逆行 → wrong way\n"
    "路口 → intersection      环岛 → roundabout      死路/断头路 → dead end\n"
    "前面 → ahead   后面 → behind   附近 → near/nearby   很远 → far\n"
    "在你左边 → on your left   在你右边 → on your right\n"
    "这里 → here   那里 → there\n"
    "\n"
    "=== PROBLEMS & ACCIDENTS ===\n"
    "我撞了/我撞车了 → i crashed       我翻了 → i flipped\n"
    "我卡车卡住了 → my truck is stuck    发动机坏了 → engine is damaged\n"
    "爆胎了 → flat tire       没油了 → out of fuel / need fuel\n"
    "挂车脱开了 → my trailer is detached    我需要拖车 → i need a tow\n"
    "服务器卡了 → server is lagging      我游戏崩了 → my game crashed\n"
    "我掉线了 → i disconnected/i dc'd      我回来了 → i'm back\n"
    "对不起我的错 → sorry my fault      不是故意的 → didn't mean to\n"
    "\n"
    "=== SOCIAL & PRAISE ===\n"
    "干得好/厉害 → good job/gj      做得好 → well done/wd\n"
    "漂亮/太棒了/牛逼 → nice/great/awesome      太厉害了 → amazing/incredible\n"
    "酷 → cool      太糟糕了/烂 → terrible/awful\n"
    "哈哈/哈哈哈/笑死 → lol/lmao/lmaooo      惨 → RIP/rip\n"
    "好运 → good luck/gl      玩开心 → have fun/hf      恭喜 → congrats\n"
    "谢谢/多谢 → thanks/thx/ty      非常感谢 → thank you so much/tysm\n"
    "没事/没关系/不客气 → np/no worries      对不起/抱歉 → sorry/sry\n"
    "不好意思/打扰了 → excuse me      我的错 → my bad\n"
    "哇/卧槽 → wow/woah      哎呀 → oops      一般般/还行 → meh/decent\n"
    "保重 → take care      再见 → see you/cya\n"
    "\n"
    "=== CHINESE SLANG & COLLOQUIALISMS ===\n"
    "好吧 → alright/fine      算了 → never mind/nvm      随便 → whatever\n"
    "当然啦 → of course/obviously      确实 → exactly/true      真的 → for real/fr\n"
    "可以的/行 → works for me/sounds good      没问题 → no problem\n"
    "等一下哈 → wait a sec      马上就来 → coming/bring    快了快了 → almost there\n"
    "搞定了/弄好了 → done/fixed    坏了/出问题了 → broken/messed up\n"
    "作妖/搞事情 → acting up/messing around     无语 → smh\n"
    "尴尬 → awkward/embarrassing    好烦 → so annoying\n"
    "笑死我了 → lmaooo/im dying    太真实了 → too real/so true\n"
    "兄弟们/各位 → guys/everyone    伙计 → mate    老哥 → bro/dude\n"
    "新人 → new player    老玩家 → veteran player    大佬 → expert/pro\n"
    "\n"
    "=== CORE RULES ===\n"
    "(1) Translate EVERY word. If Chinese has a subject, adjective, adverb, or modifier,\n"
    "    it MUST appear in English. \"你的红色卡车真好看\" is not \"nice truck\" —\n"
    "    it's \"your red truck looks really nice\".\n"
    "(2) Output ONLY the English translation. No quotes, no Chinese, no explanations.\n"
    "(3) Use natural casual English a gamer would actually type, not formal textbook English.\n"
    "(4) Never repeat the same word consecutively (no \"my my\", \"the the\", \"is is\").\n"
    "(5) Keep EXACTLY as-is: player names, place names, road numbers, numbers.\n"
    "(6) Match the original tone: joking stays joking, angry stays angry, urgent stays urgent.\n"
    "(7) If already in English, return unchanged.\n"
    "(8) \"也可以\" = \"also works\" / \"is also fine\" / \"too\". It is NEVER \"if possible\".\n"
    "(9) Don't turn statements into suggestions. \"我们走吧\" = \"lets go\", NOT \"we could go\".\n"
    "\n"
    "=== EXAMPLES ===\n"
    "嗨兄弟，你的卡车真好看 → hey bro, your truck looks really nice\n"
    "你们要去哪 → where are you guys heading\n"
    "前面右边有警察，大家小心 → cop ahead on the right, everyone watch out\n"
    "对不起我撞到你了，我的错 → sorry i hit you, my bad\n"
    "有人去加来或杜伊斯堡吗 → anyone going to Calais or Duisburg\n"
    "我货物已经损坏一半了，无语 → my cargo is already half damaged smh\n"
    "在休息区等我一下，马上回来 → wait for me at the rest stop, brb\n"
    "你现在在哪个城市 → what city are you in right now\n"
    "我觉得我迷路了，有人能帮帮我吗 → i think im lost, can anyone help me\n"
    "好车队各位，出发出发 → nice convoy guys, lets go gogogo\n"
    "要加油，最近的加油站在哪 → need fuel, wheres the nearest gas station\n"
    "这里限速80，大家慢点 → speed limit 80 here, slow down guys\n"
    "你的挂车着火了哈哈哈 → your trailer is on fire lmaooo\n"
    "这趟任务能给多少钱 → how much does this job pay\n"
    "我刚玩这个游戏，有什么建议吗 → im new to this game, any tips\n"
    "打开车灯，天快黑了 → turn on your headlights, its getting dark\n"
    "别在这超车，太危险了兄弟 → dont overtake here, too dangerous bro\n"
    "大家晚安，明天见，保重 → gn everyone, see you tomorrow, take care\n"
    "渡轮2分钟后开，快点 → ferry leaves in 2 mins, hurry up\n"
    "能帮我停一下这个挂车吗谢谢 → can you help me park this trailer, thanks\n"
    "我刚把卡车开翻了天哪 → i just flipped my truck omg\n"
    "服务器现在卡得要命 → the server is lagging so bad rn\n"
    "那个超车太帅了，说真的 → that was a sick overtake ngl\n"
    "对的，很奇怪吧，我的翻译器又在作妖了 → yeah pretty weird right, my translator is acting up again\n"
    "找个长路线吧，跑这次活动的也可以 → find a long route, or we can run the event one too\n"
    "有人有车队我能加入吗 → anyone got a convoy i can join"
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
        "temperature": 0.3,
        "max_tokens": 300,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }
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
