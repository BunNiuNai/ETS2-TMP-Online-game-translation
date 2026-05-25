# 🚛 ETS2 Chat Translator · 欧卡聊天翻译器

<p align="center">
  <img src="https://img.shields.io/badge/version-v1.1.0-brightgreen?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078D6?style=flat-square" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/downloads-GitHub%20Releases-9cf?style=flat-square" alt="Downloads">
</p>

<p align="center">
  <strong>Real-time chat translator for Euro Truck Simulator 2 / TruckersMP</strong><br>
  <sub>ETS2 / TruckersMP 联机聊天实时翻译工具</sub>
</p>

<p align="center">
  Automatically translates in-game chat into Simplified Chinese, displayed in a semi-transparent overlay.<br>
  Also supports Chinese input → English translation → send to game chat.<br>
  <sub>自动将多国语言聊天消息翻译为简体中文，以半透明悬浮窗口显示在游戏中<br>支持中文输入 → 翻译为英文 → 一键发送到游戏聊天</sub>
</p>

<p align="center">
  <a href="https://github.com/BunNiuNai/ets2-translator/releases"><b>⬇ Download 下载</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-quick-start--快速开始"><b>Quick Start 快速开始</b></a>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <a href="#-faq--常见问题"><b>FAQ 常见问题</b></a>
</p>

---

## 📖 Table of Contents / 目录

- [✨ Features / 功能特性](#-features--功能特性)
- [🧠 Recommended LLM / 推荐大模型](#-recommended-llm--推荐大模型)
- [🖥 System Requirements / 系统要求](#-system-requirements--系统要求)
- [🚀 Quick Start / 快速开始](#-quick-start--快速开始)
- [⚙️ Configuration / 配置说明](#️-configuration--配置说明)
- [📖 Usage / 使用方式](#-usage--使用方式)
- [🔧 How It Works / 运行原理](#-how-it-works--运行原理)
- [📁 Project Structure / 项目结构](#-project-structure--项目结构)
- [📦 Dependencies / 依赖](#-dependencies--依赖)
- [📸 Screenshots / 截图](#-screenshots--截图)
- [❓ FAQ / 常见问题](#-faq--常见问题)
- [📄 License / 许可证](#-license--许可证)

---

## ✨ Features / 功能特性

| Emoji | Feature | Description |
|:---:|:---|---|
| 🌐 | **Real-time Chat Translation**<br><sub>实时聊天翻译</sub> | Monitors TruckersMP chat logs, batch translates messages from any language to Chinese<br><sub>监控 TruckersMP 聊天日志，批量翻译各语言消息到简体中文</sub> |
| 📤 | **Reverse Translation & Send**<br><sub>反向翻译发送</sub> | Type Chinese → auto-translate to English → hotkey send to game chat<br><sub>输入中文 → 自动翻译为英文 → 热键发送到游戏聊天</sub> |
| 👥 | **Universal Translation**<br><sub>全员翻译</sub> | All player messages are translated equally, including your own (shown as sent)<br><sub>所有玩家的消息均等翻译，自己的消息显示为已发送</sub> |
| 📦 | **Batch Translation**<br><sub>批量翻译</sub> | Collects messages within a 0.8s window, merges into a single API request<br><sub>0.8 秒窗口内收集多条消息，合并为一次 API 请求</sub> |
| 💾 | **LRU Cache**<br><sub>LRU 缓存</sub> | 200-entry translation cache — identical messages hit cache, skipping API calls<br><sub>200 条翻译缓存，相同消息直接命中，跳过 API 调用</sub> |
| 🔀 | **Dual Translation Backend**<br><sub>双翻译后端</sub> | LLM API + Baidu Translate API — use independently or combined<br><sub>LLM API + 百度翻译 API，可独立使用或组合</sub> |
| 🛡 | **Baidu Supervision**<br><sub>百度翻译监督</sub> | Hybrid mode: LLM translates first → Baidu verifies → auto-replace on mismatch with red label<br><sub>混合模式：LLM 先翻译 → 百度对比纠错 → 不一致时自动替换并红字提示</sub> |
| 🔄 | **One-Click Auto Update**<br><sub>一键自动更新</sub> | Auto-checks GitHub for new versions on startup, right-click menu to download & install<br><sub>启动时自动检查 GitHub 新版本，右键菜单一键下载更新</sub> |
| 🧩 | **Multi-LLM Support**<br><sub>多种 LLM 支持</sub> | Compatible with OpenAI API format (OpenAI, DeepSeek, Ollama, Groq, SiliconFlow, etc.)<br><sub>兼容 OpenAI API 格式（OpenAI、DeepSeek、Ollama、Groq、硅基流动 等）</sub> |
| 🔌 | **Connectivity Test**<br><sub>连通性测试</sub> | One-click API connection test in settings; hybrid mode tests both LLM + Baidu<br><sub>设置中一键测试 API 连接，混合模式同时检测 LLM + 百度</sub> |
| 🪟 | **Dual Window Mode**<br><sub>双窗口模式</sub> | Standard window / borderless overlay; overlay supports click-through and edge-resize<br><sub>标准窗口 / 无边框悬浮窗口，悬浮模式支持鼠标穿透和边缘拖拽缩放</sub> |
| 📊 | **API Usage Stats**<br><sub>API 用量统计</sub> | Real-time display: translations, cache hits, skipped messages, and savings percentage<br><sub>窗口底部实时显示翻译次数、缓存命中、跳过次数和节省百分比</sub> |
| 📍 | **Window Position Memory**<br><sub>窗口位置记忆</sub> | Automatically saves and restores overlay & settings window position and size<br><sub>自动保存和恢复悬浮窗和设置窗口的位置与大小</sub> |
| 🎨 | **Dark Theme Settings**<br><sub>暗色主题设置</sub> | Polished dark-themed settings dialog, consistent with the overlay window<br><sub>全新暗色主题设置界面，与悬浮窗风格统一</sub> |
| 🔄 | **Chat Deduplication**<br><sub>聊天去重</sub> | Prevents duplicate display of the same chat message (player + text + timestamp)<br><sub>防止同一条聊天消息重复显示（玩家+内容+时间戳去重）</sub> |
| ✂️ | **Message Separators**<br><sub>消息分割线</sub> | White horizontal line under each message for quick visual separation<br><sub>每条翻译消息下方显示白色横线分隔，便于快速区分</sub> |
| ⌨️ | **Global Hotkey**<br><sub>全局热键</sub> | Customizable key combo (e.g. Shift+Y) to summon the translator input from in-game<br><sub>可自定义组合键（如 Shift+Y）从游戏内呼出翻译器输入栏</sub> |
| 📋 | **System Tray**<br><sub>系统托盘</sub> | Win32 tray icon with right-click quick actions (show/hide, mode switch, click-through, etc.)<br><sub>Win32 托盘图标，右键菜单快捷操作（显示/隐藏、切换模式、鼠标穿透等）</sub> |
| 💬 | **Chat Slang Translation**<br><sub>聊天俚语翻译</sub> | Built-in gaming abbreviations/slang mappings (lol→哈哈, brb→马上回来, etc.)<br><sub>内置网游缩写/俚语映射（lol→哈哈，brb→马上回来 等）</sub> |

---

## 🧠 Recommended LLM / 推荐大模型

> **For users in China / 国内用户推荐**: [SiliconFlow 硅基流动](https://siliconflow.cn/) — model `Qwen/Qwen3-8B`
>
> **For international users**: [OpenAI](https://platform.openai.com/) — model `gpt-4o-mini` (cheap & fast)
>
> ✅ SiliconFlow: free tier available · no rate limit · direct China access / 硅基流动免费额度、不限并发、国内直连
>
> Qwen models are small, fast, and accurate — ideal for translation tasks. / 通义千问小模型，翻译快、准，个人用户随便用。

| Provider / 提供商 | Model / 模型 | Pricing / 价格 | Notes / 备注 |
|:---|:---|:---|:---|
| [SiliconFlow 硅基流动](https://siliconflow.cn/) | `Qwen/Qwen3-8B` | Free tier / 免费 | Fast, China direct / 国内直连 |
| [DeepSeek](https://platform.deepseek.com/) | `deepseek-chat` | ¥1/1M tokens | Excellent quality / 质量优秀 |
| [OpenAI](https://platform.openai.com/) | `gpt-4o-mini` | $0.15/1M tokens | Cheap & reliable / 便宜可靠 |
| [Groq](https://groq.com/) | `llama-3.3-70b` | Free tier / 免费 | Ultra-fast inference / 推理极快 |
| [Ollama](https://ollama.com/) | `qwen3:8b` | Free (local) / 免费 | Runs locally, no network / 本地运行，无需网络 |

> **Tip**: Any OpenAI-compatible API works. Just fill in the endpoint, key, and model name. / 任意兼容 OpenAI API 格式的服务均可使用，填写地址、密钥和模型名即可。

---

## 🖥 System Requirements / 系统要求

| Requirement | Detail |
|:---|:---|
| **OS / 操作系统** | Windows 10 / 11 |
| **Python** | 3.10+ (not needed for exe release / exe 打包版无需 Python) |
| **Game / 游戏** | Euro Truck Simulator 2 + TruckersMP mod |

---

## 🚀 Quick Start / 快速开始

### Method 1: Run from source / 方式一：Python 源码运行

```bash
# 1. Clone / 克隆仓库
git clone https://github.com/BunNiuNai/ets2-translator.git
cd ets2-translator

# 2. Install dependencies / 安装依赖
pip install -r requirements.txt

# 3. Run / 运行
python main.py
```

### Method 2: Download exe / 方式二：下载 exe 直接运行

Download the latest `ETS2_Chat_Translator.exe` from [GitHub Releases](https://github.com/BunNiuNai/ets2-translator/releases). Double-click to run — no Python required.

从 [GitHub Releases](https://github.com/BunNiuNai/ets2-translator/releases) 下载最新的 `ETS2_Chat_Translator.exe`，双击运行即可，无需安装 Python 环境。

### Method 3: Build from source / 方式三：自行打包

```bash
python build_exe.py
# Output / 输出: dist/ETS2_Chat_Translator.exe
```

---

## ⚙️ Configuration / 配置说明

On first run, the settings window pops up automatically. You can also access it via right-click menu → **Settings / 设置**.

首次运行会自动弹出设置窗口，也可通过右键菜单 → **Settings / 设置** 打开。

Fill in your API endpoint, key, and model, then click **Test / 测试连接** to verify. Click **Save / 保存** when done.

填写 API 地址、密钥和模型后，点击 **Test / 测试连接** 验证配置是否可用，测试通过后点击 **Save / 保存**。

> 💡 Config is auto-saved to `Documents\ETS2 Translator\config.json`. No need to re-enter on next launch. Connectivity is auto-tested on each startup.
>
> 配置会自动保存到 `文档\ETS2 Translator\config.json`，下次启动无需重新填写。每次启动时自动测试 API 连通性。

| Config / 配置项 | Description / 说明 | Example / 示例 |
|:---|:---|---|
| Translation Backend / 翻译后端 | LLM / Baidu / LLM+Baidu hybrid | `LLM+Baidu 混合` |
| API Endpoint | OpenAI-compatible API URL | `https://api.openai.com/v1/chat/completions` |
| API Key | Your API key / 密钥 | `sk-xxxxxxxx` |
| Model / 模型 | Model name | `gpt-4o-mini` |
| Baidu APP ID / 百度 APP ID | Baidu Translate API APP ID | `20250101001234567` |
| Baidu Secret / 百度密钥 | Baidu Translate API secret | `xxxxxx` |
| Window Opacity / 窗口透明度 | 0.1 (transparent) ~ 1.0 (opaque) | `0.80` |
| Font Size / 字体大小 | Chat display font size | `12` |
| Max Messages / 最大消息数 | Max visible messages in window | `50` |
| Player Name / 你的游戏ID | Your in-game name (optional, auto-detected) | `PlayerName` |
| Window Mode / 窗口模式 | Standard / Overlay | `Overlay 悬浮` |
| Click-through / 鼠标穿透 | Clicks pass through to game (overlay only) | `No 否` |
| Copy Hotkey / 复制热键 | Copy translated text to clipboard | `ctrl+c` |
| Send Hotkey / 发送热键 | Confirm message sent (game's send key) | `enter` |
| Focus Hotkey / 呼出输入框热键 | Global hotkey to summon input bar | `shift+y` |

### Hotkey Setup / 热键设置

Click any hotkey label in settings → it changes to **"Press key combo..."** → press your desired key combination (e.g. Shift+Z) → auto-detected and saved.

点击设置中的热键标签 → 标签变为 **"按下组合键..."** → 直接按下键盘组合键（如 Shift+Z）→ 自动识别并保存。

> ⚠️ **IMPORTANT: Turn off Caps Lock before binding hotkeys! / 绑定按键前请锁定大写！**

---

## 📖 Usage / 使用方式

1. Launch ETS2 and join a TruckersMP server / 启动 ETS2 并进入 TruckersMP 联机模式
2. Run the translator — the window appears as overlay or standalone / 运行翻译器，窗口会以悬浮或标准模式显示
3. **View translations / 查看翻译**: Other players' messages are automatically translated and displayed / 其他玩家的消息会自动翻译并显示在窗口中
4. **Send messages / 发送消息**:
   - Press the global hotkey (default `Shift+Y`) to summon the input bar / 按全局热键（默认 `Shift+Y`）呼出输入栏
   - Type Chinese → press Enter → auto-translated to English / 输入中文 → 回车 → 自动翻译为英文
   - Translation result shown in input box → press copy hotkey to copy to clipboard / 翻译结果显示在输入框 → 按复制热键复制到剪贴板
   - Paste into game chat box manually → press send hotkey to confirm / 在游戏中手动粘贴到聊天框 → 按发送热键确认发送
5. Right-click the system tray icon for quick actions / 系统托盘图标右键可进行快捷操作
6. Right-click the translation window for the settings menu / 右键点击翻译窗口可打开设置菜单

---

## 🔧 How It Works / 运行原理

### Architecture Overview / 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      ETS2 / TruckersMP                           │
│  In-game chat ──→ writes to log file chat_YYYY-MM-DD_log.txt    │
│  游戏内聊天 ──→ 写入日志文件 chat_YYYY-MM-DD_log.txt               │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼ (incremental read / 文件增量读取)
┌─────────────────────────────────────────────────────────────────┐
│  monitor.py — Chat Log Watcher / 聊天日志监控                     │
│  · Gets Documents path from Windows registry                     │
│  · Matches log file: chat_YYYY_MM_DD_log.txt                     │
│  · Polls file size every 0.5s, reads new lines incrementally     │
│  · Regex: [Channel] [HH:MM:SS] PlayerName (TMP_ID): Message      │
│  · All messages queued equally for translation                   │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼ (raw_queue)
┌─────────────────────────────────────────────────────────────────┐
│  translator.py — Batch Translation Engine / 批量翻译引擎          │
│  · LRU cache (200 entries) — identical text hits cache           │
│  · Batch mode: 0.8s window collects messages → single API call   │
│  · Skips own messages (Chinese input)                            │
│  · Skips already-Chinese messages                                │
│  · Three backends: LLM / Baidu / LLM+Baidu hybrid                │
│  · translate_to_english(): reverse translation (Chinese→English) │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼ (display_queue)
┌─────────────────────────────────────────────────────────────────┐
│  overlay.py — Translation Display Window / 翻译显示窗口           │
│  · Polls display_queue every 250ms, merges idle refreshes        │
│  · Dual mode: Standard window / Borderless overlay               │
│  · Overlay: Win32 API click-through, drag, edge-resize           │
│  · Input bar: hotkey summon → focus grab → type directly         │
│  · Send flow: Enter → translate → show result → manual send     │
│  · Translation notifications above input bar                     │
│  · API usage stats bar                                           │
│  · Window position auto-save/restore                             │
└─────────────────────────────────────────────────────────────────┘
```

### Message Lifecycle / 消息生命周期

```
1. Player sends chat in game / 玩家在游戏内发送聊天
       │
2. TruckersMP writes to chat_YYYY_MM_DD_log.txt / 写入日志文件
       │
3. ChatMonitor detects file change, reads new lines / 检测文件变化，增量读取
       │
4. Regex parse → ChatMessage, sent to translation queue / 正则解析 → 翻译队列
       │
5. Put into raw_queue / 放入 raw_queue
       │
6. Translator picks up, checks LRU cache / 取出检查 LRU 缓存
       │   Cache hit → return directly / 命中 → 直接返回
       │   Cache miss → add to batch / 未命中 → 加入批量队列
       │
7. Batch window expires → single API request / 批量窗口到期 → 一次 API 请求
       │
8. Split result, put each into display_queue / 拆分翻译结果 → display_queue
       │
9. OverlayWindow polls queue every 250ms / 每 250ms 轮询队列
       │
10. Incremental Text update, stats refresh, auto-scroll / 增量更新、刷新统计、自动滚底
```

### Send Message Flow / 发送消息流程

```
1. User presses global hotkey (e.g. Shift+Y) in game / 在游戏中按全局热键
   │   Window brought to front, AttachThreadInput grabs focus
   │   翻译器窗口置顶，抢焦点，用户可直接输入中文
       │
2. Type Chinese, press Enter / 输入中文消息，按回车
   │   Input disabled, shows "Translating..." / 输入框禁用，显示"翻译中..."
   │   Background thread calls LLM to translate Chinese → English
   │   后台调用翻译引擎 中文 → 英文
       │
3. Translation done → result shown in input box, auto-selected
   │   翻译完成 → 结果显示在输入框并自动选中
   │   Shows "Done | Use hotkeys to send" / 显示"翻译完成 | 用热键手动发送"
   │   Manual hotkey poller started / 启动手动热键轮询器
       │
4. User presses copy hotkey (default Ctrl+C) / 用户按复制热键
   │   System handles copy, text goes to clipboard / 系统处理复制，文字进入剪贴板
   │   Translator detects key → shows "Copied to clipboard" / 显示"已复制到剪贴板"
       │
5. User opens game chat, pastes text / 用户打开游戏聊天框粘贴译文
   │   Translator not involved in this step / 翻译器不参与此步骤
       │
6. User presses send hotkey (default Enter) to send / 按发送热键发送消息
   │   Translator detects key → stops poller / 检测到按键 → 停止轮询器
   │   Sent message shown in window (Sent label) / 显示在翻译窗口（Sent 标签）
   │   Input cleared, ready for next / 输入框清空，恢复初始状态
```

---

## 📁 Project Structure / 项目结构

```
ets2-translator/
├── main.py              # Entry point, app controller, settings dialog
│                        # 入口、主控、设置对话框
├── config.py            # AppConfig model, JSON read/write, registry Documents path
│                        # 配置模型、JSON 读写、注册表获取 Documents 路径
├── monitor.py           # Chat log watcher (incremental polling, regex parsing)
│                        # 聊天日志监控（增量轮询、正则解析）
├── translator.py        # Translation engine (LLM/Baidu/hybrid, LRU cache)
│                        # 翻译引擎（LLM API / 百度 API / 混合模式、LRU 缓存）
├── overlay.py           # Display window (Tkinter + Win32 API, input bar, hotkeys)
│                        # 显示窗口（Tkinter + Win32 API、输入栏、全局热键）
├── input_sender.py      # Keyboard simulation (SendInput API, clipboard)
│                        # 键盘模拟发送（SendInput API、剪贴板）
├── tray_icon.py         # System tray icon (pure ctypes + Win32 API)
│                        # 系统托盘图标（纯 ctypes + Win32 API）
├── update.py            # Auto-update (GitHub version check, download, replace)
│                        # 自动更新（GitHub 版本检查、下载、替换重启）
├── build_exe.py         # PyInstaller build script / 打包脚本
├── requirements.txt     # Python dependencies / Python 依赖
├── icon.ico             # App icon / 程序图标
├── README.md
└── dist/                # Build output / 构建输出
    └── ETS2_Chat_Translator.exe
```

---

## 📦 Dependencies / 依赖

| Package | Purpose / 用途 |
|:---:|:---|
| `httpx` | HTTP client for calling LLM APIs / HTTP 客户端，调用 LLM API |

Tkinter is a Python standard library. System tray and keyboard simulation use pure ctypes + Win32 API — zero third-party dependencies like pystray or Pillow.

Tkinter 为 Python 标准库。系统托盘和键盘模拟均使用纯 ctypes + Win32 API，无需 pystray、Pillow 等第三方库。

---

## 📸 Screenshots / 截图

> 📌 *Screenshots coming soon — PRs welcome! / 截图待补充 — 欢迎提交 PR！*

<!--
![Translation Window 翻译窗口](screenshots/overlay.png)
![Settings Panel 设置面板](screenshots/settings.png)
![Tray Menu 托盘菜单](screenshots/tray.png)
-->

---

## ❓ FAQ / 常见问题

<details>
<summary><b>Translation shows "[Network Error] Cannot connect to API server"？<br>翻译结果显示 "[网络错误] 无法连接到 API 服务器"？</b></summary>
Check that the API Endpoint URL is correct and the network can reach it.<br>
请检查 API Endpoint 地址是否正确，网络是否能访问该地址。
</details>

<details>
<summary><b>Translation shows "[Auth Failed] Invalid API key"？<br>翻译结果显示 "[认证失败] API 密钥无效"？</b></summary>
Check that the API Key is entered correctly and hasn't expired.<br>
请检查 API Key 是否正确填写，密钥是否过期。
</details>

<details>
<summary><b>Connectivity test shows "Not Found (404)"？<br>连通性测试显示 "API 地址不存在 (404)"？</b></summary>
Make sure the endpoint includes the full path (e.g. <code>https://api.deepseek.com/v1/chat/completions</code>) and the model name is correct.<br>
请检查 API Endpoint 是否包含完整路径（如 <code>https://api.deepseek.com/v1/chat/completions</code>），以及模型名称是否正确。
</details>

<details>
<summary><b>Startup shows "Directory not found" or "No chat log files"？<br>启动后显示"目录不存在"或"目录存在但无聊天日志文件"？</b></summary>
Make sure TruckersMP is installed and you've joined an online server at least once. The log directory is at <code>Documents\ETS2MP\logs\</code> and is created automatically on first join.<br>
请确认已安装 TruckersMP 并至少进入过一次联机服务器。日志目录位于 <code>文档\ETS2MP\logs\</code>，首次进入游戏后会自动创建。
</details>

<details>
<summary><b>Log file exists but chat messages aren't recognized？<br>能看到日志文件但无法识别聊天内容？</b></summary>
If your TruckersMP version is very old, the log format may differ. Please update TruckersMP to the latest version.<br>
如果 TruckersMP 版本较旧，日志格式可能不同。请更新 TruckersMP 客户端到最新版本。
</details>

<details>
<summary><b>Translation window is not visible？<br>为什么看不到翻译窗口？</b></summary>
Check if the window is off-screen; right-click the tray icon → "Show/Hide" to toggle; try switching to Standard window mode in settings.<br>
检查窗口是否在屏幕外；右键系统托盘图标选择 "Show/Hide" 切换显示；尝试切换到标准窗口模式。
</details>

<details>
<summary><b>Can't click/drag the window in overlay mode?<br>悬浮模式下无法点击/拖拽窗口？</b></summary>
If click-through is enabled, the window won't receive mouse clicks. Disable click-through via the tray menu first.<br>
如果开启了鼠标穿透，窗口不接受鼠标点击。请通过系统托盘菜单关闭点击穿透后再操作。
</details>

<details>
<summary><b>Global hotkey doesn't summon the input bar？<br>按热键无法呼出输入栏？</b></summary>
Verify the hotkey is set correctly (click the hotkey label in settings and press the combo directly). Note that the hotkey may be intercepted by other programs or the game.<br>
请确认热键设置正确（在设置中点击热键标签后直接按组合键重新设置）。注意全局热键可能被其他程序或游戏拦截。
</details>

<details>
<summary><b>Pressing the hotkey also opens the game chat？<br>热键按下后游戏聊天框也打开了？</b></summary>
The translator uses AttachThreadInput + SetForegroundWindow to grab focus from the game. If issues persist, try a different hotkey combo.<br>
翻译器会通过 AttachThreadInput + SetForegroundWindow 抢占焦点，输入焦点会从游戏转移到翻译器。如果仍有问题，尝试更换热键组合。
</details>

<details>
<summary><b>How to send translated text to the game?<br>翻译完成后如何发送到游戏？</b></summary>
After translation, press the copy hotkey (default Ctrl+C) to copy to clipboard, then open the game chat box and paste (Ctrl+V), press send hotkey (default Enter) to send.<br>
翻译结果显示后，按复制热键（默认 Ctrl+C）将文本复制到剪贴板，然后在游戏中手动打开聊天框粘贴（Ctrl+V），按发送热键（默认 Enter）发送。
</details>

<details>
<summary><b>"Translation failed" when sending a message？<br>发送消息时提示"翻译失败"？</b></summary>
Check that your API configuration is correct and the API is accessible.<br>
请检查 API 配置是否正确，确保 API 可以正常访问。
</details>

<details>
<summary><b>What's the difference between Baidu and LLM translation?<br>百度翻译和 LLM 翻译有什么区别？</b></summary>
Baidu Translate is a dedicated neural machine translation engine — more accurate and faster, with 5M characters/month free on the standard plan. LLM translation is more flexible but may be less consistent. The <b>LLM + Baidu hybrid</b> mode is recommended.<br>
百度翻译是专业神经机器翻译引擎，翻译更准确、速度更快，标准版每月 500 万字符免费。LLM 翻译更灵活但可能不够稳定。推荐使用 <b>LLM + 百度监督</b> 混合模式。
</details>

<details>
<summary><b>How to apply for Baidu Translate API?<br>如何申请百度翻译 API？</b></summary>
Visit <a href="https://fanyi-api.baidu.com/">fanyi-api.baidu.com</a>, register as a developer, create an app to get the APP ID and secret. Choose the "Standard" plan for free usage.<br>
访问 <a href="https://fanyi-api.baidu.com/">fanyi-api.baidu.com</a> 注册成为开发者，创建应用获取 APP ID 和密钥。选择"标准版"即可免费使用。
</details>

<details>
<summary><b>How to update to the latest version?<br>如何更新到新版本？</b></summary>
Updates are auto-checked on startup. When a new version is found, right-click menu → <b>Check Updates / 检查更新</b> to auto-download and install.<br>
启动时自动检查更新，有新版会在窗口提示。右键菜单 → <b>Check Updates / 检查更新</b> 即可自动下载并安装更新。
</details>

<details>
<summary><b>Font size changes don't take effect immediately?<br>调整字体大小后没有立即生效？</b></summary>
As of v1.0.9, font size changes apply instantly when you save settings — no restart needed. As of v1.1.0, the settings dialog uses a dark theme and remembers its window size.<br>
从 v1.0.9 开始，字体大小调整保存后即时生效，无需重启。从 v1.1.0 开始，设置界面采用暗色主题并记忆窗口尺寸。
</details>

---

## 📄 License / 许可证

This project is open source under the [MIT License](LICENSE). Completely free to use.

本项目基于 [MIT License](LICENSE) 开源，完全免费，可放心使用。

<p align="center">
  <sub>Made with ❤️ for the ETS2 TruckersMP community</sub>
</p>
