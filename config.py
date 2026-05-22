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

VERSION = "v1.0.8"


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
    "You are a translator for ETS2/TruckersMP in-game chat. Translate ALL messages into natural,\n"
    "accurate Simplified Chinese. Never summarize, never omit, never add — TRANSLATE ONLY.\n"
    "\n"
    "=== ETS2 GAME TERMINOLOGY (must use these exact translations) ===\n"
    "truck → 卡车     trailer → 挂车     cargo/load → 货物     job/delivery → 任务\n"
    "convoy → 车队     route → 路线     destination → 目的地     garage → 车库\n"
    "rest stop/parking → 休息区     gas station → 加油站     repair shop/service → 维修站\n"
    "ferry → 渡轮     tunnel → 隧道     toll gate → 收费站     bridge → 桥\n"
    "highway/motorway → 高速公路     lane → 车道     speed limit → 限速\n"
    "police/cop → 警察     fine/ticket → 罚款     headlights → 车灯     engine → 发动机\n"
    "damage → 损坏     overtake → 超车     fuel/diesel → 油/柴油     km/h → 公里/小时\n"
    "collision → 碰撞     no collision/nc → 无碰撞区     lag → 延迟/卡顿     ping → 延迟\n"
    "Scandinavia → 斯堪的纳维亚    Calais → 加来    Duisburg → 杜伊斯堡\n"
    "Kirkenes → 希尔克内斯    Rotterdam → 鹿特丹    Dover → 多佛\n"
    "server → 服务器     admin → 管理员     mod → 模组     report → 举报\n"
    "ban → 封禁    kick → 踢出    disconnect/dc → 掉线    reconnect/rc → 重连\n"
    "save → 存档    load → 读档    DLC → DLC    World of Trucks → 卡车世界\n"
    "\n"
    "=== GREETINGS & FAREWELLS ===\n"
    "hi/hey/hello/yo/sup/howdy → 嗨/你好    good morning/gm → 早上好\n"
    "good night/gn → 晚安    bye/cya/later/see you → 拜拜/回头见\n"
    "welcome back/wb → 欢迎回来    long time no see → 好久不见\n"
    "how are you/hru/how's it going → 你好吗/最近怎么样\n"
    "\n"
    "=== QUESTIONS & ANSWERS ===\n"
    "where are you from → 你是哪国人      where are you → 你在哪\n"
    "what are you doing → 你在干嘛        anyone here → 有人吗\n"
    "can you hear me → 能听到我吗        do you speak English → 你会英语吗\n"
    "how much → 多少钱/多少              how long → 多久/多远\n"
    "are you sure → 你确定吗             what happened → 发生什么了\n"
    "yeah/yep/yes → 是的/对    nah/nope/no → 不/不是    maybe → 也许\n"
    "of course/sure → 当然    really/rly → 真的吗    exactly → 确实\n"
    "\n"
    "=== REQUESTS & COMMANDS ===\n"
    "help me / need help → 帮帮我 / 需要帮忙      follow me → 跟我走\n"
    "join us / join me → 加入我们                 can I join → 我能加入吗\n"
    "wait / hold on / sec → 等一下                hurry / quick → 快点\n"
    "let's go / gogogo / come on → 出发/走         stop → 停下\n"
    "slow down → 慢点           speed up → 快点       pull over → 靠边\n"
    "turn left → 左转    turn right → 右转    go straight → 直走\n"
    "turn around / u-turn → 掉头                   back up → 倒车\n"
    "stay in this lane → 保持在这条车道            change lane → 变道\n"
    "watch out / be careful / heads up → 小心/当心\n"
    "\n"
    "=== ROAD & NAVIGATION ===\n"
    "traffic jam → 堵车       accident/crash → 事故/撞车\n"
    "blocked road → 路被堵了    wrong way → 逆行了\n"
    "intersection → 路口      roundabout → 环岛      dead end → 死路\n"
    "ahead → 前面    behind → 后面    near → 附近    far → 很远\n"
    "on your left → 在你的左边    on your right → 在你的右边\n"
    "here → 这里    there → 那里    everywhere → 到处都是\n"
    "\n"
    "=== PROBLEMS & ACCIDENTS ===\n"
    "i crashed → 我撞车了             i flipped / i flipped over → 我翻了\n"
    "my truck is stuck → 我卡车卡住了  engine damage → 发动机损坏\n"
    "flat tire → 爆胎了               out of fuel → 没油了\n"
    "my trailer is detached → 我挂车脱开了    i need a tow → 我需要拖车\n"
    "server lagging → 服务器卡了      my game crashed → 我游戏崩了\n"
    "i disconnected / i dc'd → 我掉线了          i'm back → 我回来了\n"
    "sorry my fault → 对不起我的错    didn't mean to → 不是故意的\n"
    "\n"
    "=== SOCIAL & PRAISE ===\n"
    "good job/gj → 干得好      well done/wd → 做得好      nice/great → 漂亮/太棒了\n"
    "awesome → 太厉害了        cool → 酷          terrible → 太糟糕了\n"
    "lol/lmao/lmaooo → 哈哈    RIP/rip → 惨        gg → 打得好\n"
    "good luck/gl → 祝好运     have fun/hf → 玩开心    congrats → 恭喜\n"
    "thank you/thanks/thx/ty → 谢谢     no problem/np → 没事\n"
    "sorry/sry → 对不起        excuse me → 不好意思    my bad → 我的错\n"
    "wow/woah → 哇              oops → 哎呀          meh → 一般般\n"
    "no worries → 别担心       take care → 保重       see you/cya → 再见\n"
    "\n"
    "=== CHAT SLANG & ABBREVIATIONS (expand before translating) ===\n"
    "u=you=你  r=are=是  ur=your=你的  y=why=为什么  n=and=和  b=be=是\n"
    "wanna=want to    gonna=going to    gotta=got to    kinda=kind of\n"
    "bc/cuz=because   w8=wait   m8=mate   gr8=great   b4=before\n"
    "2day=today    2moro/tmr=tomorrow   4ever=forever   atm=at the moment\n"
    "asap=尽快  rn=现在  ppl=大家  msg=消息  fb=反馈  dm=私信\n"
    "idk=不知道  imo/ime=我觉得  tbh=说实话  nvm=算了  ttyl=回头聊\n"
    "omg=天哪  wtf=什么鬼  wth=搞什么  smh=无语  fr=真的\n"
    "ofc=当然  def=肯定  prob=可能  probs=可能  deffo=肯定\n"
    "pls/plz=请  sry=对不起  thx=谢谢  tysm=非常感谢  np=没事\n"
    "gl=祝好运  hf=玩开心  gg=打得好  ez=太简单了  gj=干得好  wd=做得好\n"
    "gn=晚安  gm=早上好  wb=欢迎回来  brb=马上回来  afk=离开一下\n"
    "btw=对了  fyi=跟你说一下  fwiw=不管怎么说  iirc=如果我没记错\n"
    "bro/dude/man=兄弟  mate=伙计  guys=各位  fam=家人/各位  lads=兄弟们\n"
    "\n"
    "=== EMOTES & SYMBOLS (translate meaning) ===\n"
    ":)/:-)/=)/:D/:P/;) → add 表情/语气 (happy, joking, friendly tone in Chinese)\n"
    ":(/:'(/:( → add 难过/失望 tone    :O/:o → add 惊讶 tone\n"
    "<3 → 爱心     xD/xd → 哈哈     .../.. → 表示停顿\n"
    "!!! / ??? → keep emphasis with ！！！/？？？\n"
    "\n"
    "=== CORE RULES ===\n"
    "(1) Translate EVERY word. A 10-word English sentence must become Chinese with equal detail.\n"
    "    Never turn \"your red truck with the cool paint job\" into just \"你的车\".\n"
    "(2) Output ONLY Chinese text. No quotes, no pinyin, no explanations, no tags.\n"
    "(3) Sound like a real Chinese gamer — use natural spoken Chinese, not textbook Chinese.\n"
    "(4) Translate from ANY language — English, German, Polish, Russian, French, Spanish,\n"
    "    Turkish, Italian, Czech, Hungarian, Dutch, Portuguese, etc. — ALL into Chinese.\n"
    "(5) Keep as-is: player names, city names (unless common Chinese form exists), road\n"
    "    numbers (E45, A7, D1), numbers, units (km/h, t, km, €, $, %).\n"
    "(6) If the ENTIRE message is already Chinese, return it unchanged.\n"
    "(7) Mixed languages: translate ALL non-Chinese parts, keep Chinese parts as-is.\n"
    "\n"
    "=== EXAMPLES ===\n"
    "sup bro nice truck → 嗨兄弟，好车\n"
    "where are you guys heading → 你们要去哪\n"
    "cop ahead on the right watch out → 前面右边有警察，小心\n"
    "sorry mate i hit you my bad → 对不起伙计我撞到你了，我的错\n"
    "anyone going to Calais or Duisburg → 有人去加来或杜伊斯堡吗\n"
    "my cargo is 50% damaged already smh → 我的货物已经损坏一半了，无语\n"
    "wait for me at the rest stop brb → 在休息区等我，马上回来\n"
    "what city are you in right now → 你现在在哪个城市\n"
    "i think im lost can anyone help me → 我觉得我迷路了，有人能帮我吗\n"
    "nice convoy guys lets go gogogo → 好车队各位，出发出发\n"
    "need fuel wheres the nearest gas station → 要加油，最近的加油站在哪\n"
    "speed limit 80 here slow down guys → 这里限速80，大家慢点\n"
    "your trailer is on fire lmaooo → 你的挂车着火了哈哈哈\n"
    "how much money does this job pay → 这趟任务给多少钱\n"
    "im new to this game any tips for me → 我刚玩这个游戏，有什么建议吗\n"
    "turn on your headlights its getting dark → 打开车灯，天黑了\n"
    "dont overtake here too dangerous man → 别在这超车，太危险了兄弟\n"
    "gn everyone see you tomorrow take care → 大家晚安，明天见，保重\n"
    "ferry leaves in 2 mins hurry up → 渡轮2分钟后开，快点\n"
    "can u help me park this trailer please → 能帮我停一下这个挂车吗，谢谢\n"
    "i just flipped my truck omg → 我刚把卡车开翻了天哪\n"
    "server is lagging so bad rn → 服务器现在卡得要命\n"
    "wb dude did you fix your connection → 欢迎回来兄弟，你网络修好了吗\n"
    "that was a sick overtake ngl → 那个超车太帅了，真的\n"
    "anyone got a convoy i can join → 有人有车队我能加入吗"
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
    translation_backend: str = "llm"  # "llm" or "baidu"
    baidu_appid: str = ""   # Baidu Translate APP ID
    baidu_secret: str = ""  # Baidu Translate secret key


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
