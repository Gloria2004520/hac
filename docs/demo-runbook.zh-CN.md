# 本地演示手册 · slowly / CookClip

这份文档是为了「把这套装起来、跑起来、拿手机演示」而写的，只讲怎么做，不讲为什么。

**两种用法，按需选一种：**

- **在 Mac 上部署、用 iPhone 访问** → 直接跳到 **第 8 节「Mac 部署 + iPhone 访问：完整走一遍」**，
  那一节是自成一体的完整流程，不用看前面的 Windows 部分。
- **在 Windows 上部署** → 按顺序看第 1～6 节；第 7 节是 macOS 差异速查，
  第 8 节是 Mac + iPhone 的专用手册。

> 本机已验证的版本：Python 3.13.14、Node 22.22.2、ffmpeg 6.0、yt-dlp 2026.08.19。

---

## 0. 架构：谁连谁

```
手机浏览器 / 电脑浏览器
        │  http://<局域网IP>:8766
        ▼
   前端 Node（frontend/server.cjs）   监听 0.0.0.0:8766
        │  代理转发 + 自己处理 /api/chat
        ▼
   后端 FastAPI（backend/app/main.py） 监听 127.0.0.1:8000
        │
        ├── yt-dlp  → 检索 / 下载 YouTube
        ├── ffmpeg  → 合并音视频、切点检测、抽帧
        └── 模型 API → 对话、步骤卡、判定
```

两个关键点：

1. **手机只需要访问 8766 一个端口。** 后端只绑 `127.0.0.1`，由前端代理转发过去——
   这样局域网打不到后端那一层。
2. **反爬、下载、模型都在后端**，前端只是壳。所以前端换成什么形态都不影响这些能力。

---

## 1. 首次环境搭建（只做一次）

### 1.1 克隆

```bash
git clone https://github.com/suonnnnnnn/slowly-demo.git
cd slowly-demo
```

### 1.2 Python 环境与依赖

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt
```

macOS / Linux 用 `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`。

### 1.3 装 ffmpeg 和 ffprobe

**两个都要装。** 只装 ffmpeg 不够——后端用 ffprobe 读视频时长，缺了会直接报错。

> macOS 上用 `brew install ffmpeg` 最简单（自带 ffprobe，也自动进 PATH），
> 详见 7.2。下面是国内网络下的手动办法。

国内网络别从 gyan.dev 或 GitHub 硬下（实测只有 40KB/s 左右，一个包要几十分钟）。
走 npm 二进制镜像，秒级完成：

```bash
BASE="https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.0"
DEST="/c/Users/<你的用户名>/.workbuddy/binaries/ffmpeg/bin"
mkdir -p "$DEST" && cd "$DEST"
curl -sL -o ffmpeg.gz  "$BASE/ffmpeg-win32-x64.gz"
curl -sL -o ffprobe.gz "$BASE/ffprobe-win32-x64.gz"
gunzip -c ffmpeg.gz  > ffmpeg.exe
gunzip -c ffprobe.gz > ffprobe.exe
rm -f *.gz && chmod +x *.exe
./ffmpeg.exe -version && ./ffprobe.exe -version
```

macOS / Linux 把 `win32-x64` 换成 `darwin-arm64` / `darwin-x64` / `linux-x64` / `linux-arm64`，
输出文件名去掉 `.exe`。

### 1.4 配置 `.env`

```bash
cp .env.example .env
```

在 `.env` 里**至少要改这三处**：

| 变量 | 填什么 | 说明 |
| --- | --- | --- |
| `MODEL_API_BASE` | `https://api.deepseek.com/v1` | 用 DeepSeek 官方 API |
| `MODEL_API_KEY` | `sk-你的密钥` | **绝不要提交** |
| `MODEL_NAME` | `deepseek-chat` | 推理模型用 `deepseek-reasoner` |
| `FFMPEG_LOCATION` | `C:/Users/<你>/.workbuddy/binaries/ffmpeg/bin` | 指向 1.3 的 `bin` 目录 |

`.env` 已被 `.gitignore` 忽略，不会进版本库。

### 1.5 验证

```bash
cd backend
../.venv/Scripts/python.exe -c "from app.main import app; print('import ok')"
../.venv/Scripts/python.exe -c "from app import video_analysis as v; print(v.ffmpeg_path(), v.ffprobe_path())"
```

第二条要打印出两个真实路径。打印不出来就是 `FFMPEG_LOCATION` 配错了。

---

## 2. 日常启动（每次演示前）

**开两个终端**，各跑一个：

```bash
# 终端 1 —— 后端
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000

# 终端 2 —— 前端
cd frontend
node server.cjs
```

看到这两行就对了：

```
INFO:     Uvicorn running on http://127.0.0.1:8000
Local demo: http://127.0.0.1:8766
```

想改代码自动重载，给后端加 `--reload`。

**这一段终端输出就是「日志」** —— 这个项目不写日志文件。想顺手存成文件方便事后排查，
见 §6「出问题了先看哪里：日志」。

**改过 `.env` 一定要重启对应服务。** 前端和后端都是启动时读一次配置，改完不重启不生效。

---

## 3. 手机当 App 用（PWA）

这套页面已经是一个 PWA：`frontend/dist/manifest.webmanifest` + `dist/sw.js` + `dist/icons/`。
手机上「添加到主屏幕」就是全屏带图标的 App，不用上架、不用改代码。

### ⚠️ 先说清楚手机上的一个限制：局域网 HTTP 不算「安全上下文」

浏览器规定 service worker 只能在**安全上下文**里注册：HTTPS，或者 `localhost` / `127.0.0.1`。
`http://172.20.10.2:8766` 这种局域网 IP 走明文 HTTP，**不是安全上下文**。

实际后果：

- **iOS Safari**：「添加到主屏幕」照常可用，打开是全屏、有自己的图标
  （manifest 的 `display: standalone` 生效，页面里也带了 `apple-mobile-web-app-capable`）。
  但 `dist/sw.js` **不会注册**，离线缓存不生效。
- **Android Chrome**：不会弹出「安装应用」，只能「添加到主屏幕」建个普通快捷方式，
  同样没有离线缓存。

一句话：**能当 App 用，但没有离线兜底。**

想让 service worker 真正跑起来，只有两条路：

| 办法 | 做法 | 适合 |
| --- | --- | --- |
| DevTools 端口转发（推荐 Android） | 手机 USB 连电脑 → 电脑 Chrome 打开 `chrome://inspect` → Port forwarding → 设备端口 `8766` 转到 `localhost:8766` → 手机访问 `http://localhost:8766`（这算安全上下文） | Android + 一根数据线；不用改网络、不用证书 |
| 上 HTTPS 隧道 | `ngrok http 8766` 或 `cloudflared tunnel --url http://localhost:8766`，用给出的 `https://…` 打开 | 任何设备；但会把服务暴露到公网，**没有登录的 demo 慎用** |

不想折腾也没关系——演示真正要的「全屏 + 有图标」在 iOS 上是能实现的，
离线缓存属于锦上添花。

### 3.1 打开局域网访问

> **网络默认走 iPhone 个人热点**：让电脑连手机的热点，而不是两边都连场馆 WiFi。
> 这样能绕开公共 WiFi 的客户端隔离（「手机打不开」最常见的原因），也不会把
> 没有登录的 demo 暴露给同一个 WiFi 的陌生人。下面 3.1 / 3.2 照常做即可。

在 `.env` 里把 `HOST` 那行的注释去掉：

```
HOST=0.0.0.0
```

重启前端。启动日志会打印所有局域网地址：

```
Local demo: http://127.0.0.1:8766
  on your phone: http://192.168.150.1:8766     ← VMware 虚拟网卡，忽略
  on your phone: http://192.168.79.1:8766      ← VMware 虚拟网卡，忽略
  on your phone: http://172.20.10.2:8766       ← 用这个（连 iPhone 热点时通常是 172.20.10.x）
```

**怎么挑对的那个：** 和手机在同一个网段的就是对的。
`192.168.x.1` 结尾、名字带 VMware / VirtualBox 的一律忽略——那是虚拟网卡，手机到不了。

### 3.2 防火墙放行（Windows 必做）

Windows 防火墙默认拒绝所有入站连接，没有放行规则时手机一定连不上。

用**管理员**权限开一个 PowerShell 或 CMD 窗口，跑：

```
netsh advfirewall firewall add rule name="slowly-demo 8766" dir=in action=allow protocol=TCP localport=8766
```

> 这一步需要管理员权限，普通权限的窗口加不了。

### 3.3 手机打开并安装

1. 手机连**同一个 WiFi / 热点**
2. 浏览器打开 `http://<上一步挑出的IP>:8766`
3. iOS：**必须用 Safari**（只有 Safari 有「添加到主屏幕」）→ 分享 → **添加到主屏幕**；
   Android Chrome：菜单 → **安装应用**
4. 之后从桌面图标进，全屏无地址栏

> **Mac + iPhone 的话**，这一节后半段和 3.4 的排查表偏 Windows，
> 请直接用 **第 8 节**的完整流程（8.8 讲网络怎么接，8.11 是 iPhone 专用的排查顺序）。

### 3.4 连不上？按这个顺序查

| 现象 | 原因 | 怎么办 |
| --- | --- | --- |
| 完全打不开、转圈 | 防火墙没放行 | 跑 3.2 的脚本 |
| 完全打不开，防火墙已放行 | WiFi 有**客户端隔离**（校园网/酒店/商场常见） | **手机开热点，电脑连热点** |
| 电脑上也打不开 `http://<IP>:8766` | 服务没绑到局域网 | 检查 `.env` 的 `HOST=0.0.0.0` 并重启前端 |
| 换了网络后手机打不开 | IP 变了 | 看前端启动日志里的新地址 |
| 用虚拟网卡地址打不开 | 挑错了网卡 | 选和手机同网段、有默认网关的那个 |

**判断是不是 WiFi 隔离：** 电脑浏览器打开 `http://<IP>:8766` 能开，但手机上打不开 → 就是隔离。

---

## 4. 演示当天检查清单

演示前 15 分钟逐条过一遍：

- [ ] 后端、前端两个终端都起来了，没有报错
- [ ] 电脑连的是**自己的手机热点**（不是场馆 WiFi，避开设备隔离和陌生人蹭用）
- [ ] 防火墙已放行（Windows：3.2；macOS：8.9，通常不用手动加）
- [ ] 手机上打开过一遍 `http://<IP>:8766`，页面正常
- [ ] 已经「添加到主屏幕」，从桌面图标能进
- [ ] **完整跑一遍**：提问 → 搜到视频 → 教程分解 → 步骤页出来
- [ ] 手机亮度调高、开勿扰或静音、电量够
- [ ] 准备好兜底话术：万一 YouTube 连不上，直接讲步骤页已经拆好的那条

> **最需要提前防的翻车点：现场 YouTube 突然连不上。**
> 建议提前下好一条视频留在本地，演示时直接进步骤页，不依赖当场检索。
> 这一步还没做，是下一步最值得做的加固。

---

## 5. 收尾（演示完务必做）

这个 demo **没有任何登录**，局域网开着 = 同一个网络的人都能用你的后端和你的模型密钥。

1. **删掉防火墙规则**（Windows）：管理员窗口跑
   `netsh advfirewall firewall delete rule name="slowly-demo 8766"`
   （macOS 没有这条规则，跳过；如果关过系统防火墙，记得开回来）
2. **`HOST` 改回 `127.0.0.1`**（或注释掉），重启前端
3. 关掉两个终端，停掉服务

---

## 6. 常见问题

### 出问题了先看哪里：日志

**这个项目不写日志文件。** 后端只有 `logging.getLogger("cookclip.*")`、没配任何 handler，
前端是 `console.log`。两者的日志都只走**终端标准输出**。所以「日志」就是
你启动服务的那两个终端窗口 —— 别去找 `.log` 文件，项目里没有。

出问题时按这个顺序看：

| 来源 | 能看到什么 |
| --- | --- |
| 跑 uvicorn 的终端（终端 1） | 后端报错和**完整 traceback**。要用得最多的就是这个 |
| 跑 `node server.cjs` 的终端（终端 2） | 前端代理层的失败，例如 `Binary proxy failed: ...` |
| 浏览器 F12 → Console / Network | 页面 JS 报错；每个请求的真实状态码（200 / 404 / 500 / 504） |

**想把日志留档**（演示当天很有用：手机端看不到终端，事后也能翻）：

```bash
# 终端 1 —— 后端
cd backend
../.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > ../backend.log 2>&1

# 终端 2 —— 前端
cd frontend
node server.cjs > ../frontend.log 2>&1
```

之后 `type backend.log` 就能看（macOS/Linux 用 `tail -f backend.log`，能持续刷新）。

**几条高频报错速查**：

| 日志里看到 | 含义 |
| --- | --- |
| `QueuePool limit of size ... reached, connection timed out` | 数据库连接池被占满 → 之后**所有**接口一起超时。典型场景是**正在播视频时**去开素材库/列表就 504。已修（流式端点不再握着连接）；若再出现，说明又有地方在长时间占连接 |
| 页面 `504` / 前端窗口 `backend_timeout` | 后端某个请求超过了前端代理的 **15 秒**上限。504 是**代理**给的，不是后端 |
| 页面 `502` / 前端窗口 `backend_down` | 后端没起或已崩 —— 先去终端 1 看 |
| `ffmpeg is not installed` | `FFMPEG_LOCATION` 没配、或 ffmpeg 不在 PATH（见 §1.3） |
| `Server process ... exited` / 终端 1 整个报错退出 | 后端崩了。终端 1 最后那段 traceback 就是原因 |

### YouTube 下载或检索失败

先在 `backend/` 下跑一次带详细日志的命令，看它到底用了哪个客户端、报什么：

```bash
../.venv/Scripts/python.exe -m yt_dlp --verbose --skip-download --simulate "<视频链接>"
```

按报错对症下药：

| 报错原文 | 含义 | 处理 |
| --- | --- | --- |
| `Sign in to confirm you're not a bot` | 被判定为机器人 | 配 cookies；或换网络出口 |
| `Unable to download webpage` / `timed out` | 网络到不了 | 给服务进程设代理 |
| `some formats may be missing` | 缺 JS runtime | 见下方「JS runtime」 |
| `HTTP Error 429` | 限流 | 等几分钟；搜索已有缓存 |
| `Sign in to confirm your age` | 年龄限制 | 需要登录过的 cookies |
| `Video unavailable` | 下架 / 地区限制 | 换一条视频 |

**JS runtime 当前是缺的。** yt-dlp 默认只认 deno，本机装了 node 但没显式指定，会被判为
`node (unavailable)`。这是「有时行有时不行」的主要来源之一。修法是在 yt-dlp 选项里加：

```python
{"js_runtimes": {"node": {}}}
```

注意**必须是 dict**，传成列表 `['node']` 会报
`Invalid js_runtimes format, expected a dict of {runtime: {config}}`。

### cookies 怎么给

`--cookies-from-browser chrome` 在 Windows 上**目前不可用**，实测 Chrome 和 Edge 都报：

```
ERROR: Could not copy Chrome cookie database.
```

可行做法是用浏览器扩展导出一份 Netscape 格式的 cookie 文件，然后：

```
YT_DLP_COOKIE_FILE=文件路径
```

注意：**检索那条路径只支持 cookie 文件，不支持 cookies-from-browser**，两边行为不一致。

### 模型相关

| 现象 | 原因 |
| --- | --- |
| `服务端尚未配置密钥` | `.env` 里 `MODEL_API_KEY` 是空的 |
| `模型服务返回 401` | 密钥无效 / 余额不足 / 模型名不对 |
| `模型请求受限（429）` | 上游限流，稍后再试 |
| 聊天能用但**步骤页文字是通用模板** | 模型没答上来，会如实标注，不是 bug |

---

## 7. macOS 上的差异

整体流程完全一样，下面只列不一样的地方。

### 7.1 装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

需要 Python 3.12+。macOS 自带的 `python3` 常常偏旧，不够用就 `brew install python@3.12`。

### 7.2 ffmpeg

macOS 上最省事的是 Homebrew，装完自带 ffprobe，也自动进 PATH：

```bash
brew install ffmpeg
```

这种情况下 `.env` 里的 `FFMPEG_LOCATION` **留空**即可——后端会自己在 PATH 里找。

不想用 brew 才需要手动下静态包：把 `win32-x64` 换成 `darwin-arm64`（M 系列芯片）或
`darwin-x64`（Intel），输出文件名**不带 `.exe`**，别忘了 `chmod +x`。

### 7.3 启动命令

```bash
# 终端 1 —— 后端
cd backend && ../.venv/bin/python -m uvicorn app.main:app --port 8000

# 终端 2 —— 前端
cd frontend && node server.cjs
```

注意虚拟环境路径是 `.venv/bin/`（Windows 是 `.venv\Scripts\`）。

### 7.4 查本机局域网 IP

```bash
ipconfig getifaddr en0     # Wi-Fi
ipconfig getifaddr en1     # 有线（视机型而定）
```

启动日志也会打印，以日志为准。macOS 上不会有 VMware 那种虚拟网卡干扰。

### 7.5 防火墙与「本地网络」权限

macOS **没有** Windows 那种「入站默认全拒」的机制，**通常不需要手动加放行规则**。

- 「系统设置 → 网络 → 防火墙」如果开着，可能拦；关掉或把 Node 加进允许列表
- **「本地网络」权限（macOS 15 Sequoia 起）**：按 Apple 官方文档，**接受入站连接本身不需要**
  这个权限。但如果弹出了「允许"终端"查找本地网络中的设备吗?」，点允许；
  误拒了就去「系统设置 → 隐私与安全性 → 本地网络」打开

完整说明和排查顺序见 **8.9 / 8.11**（那一节是 Mac + iPhone 的专用完整流程）。

### 7.6 cookies 与钥匙串

macOS 上用 `--cookies-from-browser chrome` 会触发**钥匙串（Keychain）授权弹窗**，
需要手动确认。不想处理就用 Firefox，或按第 6 节导出 Netscape 格式的 cookie 文件。

### 7.7 端口不需要 sudo

8000 和 8766 都大于 1024，普通用户直接就能监听。

### 7.8 收尾

没有防火墙规则要删，把 `.env` 里的 `HOST` 改回 `127.0.0.1`（或注释掉）再重启前端就行。

---

## 8. 【专用】Mac 部署 + iPhone 访问：完整走一遍

> 这一节是**自成一体的**，只讲 Mac 和 iPhone 的路径，不需要看前面 Windows 的部分。
> 从头到尾照着做即可。

### 8.1 一次性准备

```bash
xcode-select --install          # 提供 git 等命令行工具
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 node   # Node 需要 18+
```

核对：

```bash
git --version && python3 --version && node --version
```

Python 要 3.12 或更高。macOS 自带的 `python3` 常常偏旧，装了 brew 版记得让它优先。

### 8.2 拿代码 + 装依赖

```bash
git clone https://github.com/suonnnnnnn/slowly-demo.git
cd slowly-demo
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

以后**每开一个新终端**都要先 `source .venv/bin/activate`。
懒得激活就直接用全路径 `.venv/bin/python`（下面 8.5 就是这么写的）。

### 8.3 装 ffmpeg（顺手就带了 ffprobe）

```bash
brew install ffmpeg
```

brew 装完 ffmpeg 和 ffprobe 都在 PATH 上，所以 `.env` 里的 **`FFMPEG_LOCATION` 留空**即可。
校验：

```bash
ffmpeg -version | head -1 && ffprobe -version | head -1
```

### 8.4 配 `.env`

```bash
cp .env.example .env
open -e .env          # 或 code .env
```

至少改这三处：

```
MODEL_API_BASE=https://api.deepseek.com/v1
MODEL_API_KEY=sk-你的密钥
MODEL_NAME=deepseek-chat
```

`HOST` 这一步先不用动。**密钥绝不要提交**——`.env` 已在 `.gitignore` 里。

### 8.5 先在 Mac 本机跑通（别跳过这步）

```bash
# 终端 1 —— 后端
cd backend
../.venv/bin/python -m uvicorn app.main:app --port 8000

# 终端 2 —— 前端
cd frontend
node server.cjs
```

Mac 上打开 http://127.0.0.1:8766 ，能看到聊天首页就说明本机这半边 OK 了。
**先把这一步走通再碰手机**，否则手机连不上时分不清是谁的问题。

### 8.6 打开局域网访问

`.env` 里把 `HOST` 那行改成：

```
HOST=0.0.0.0
```

**重启前端**（Ctrl+C 再 `node server.cjs`）。日志会打印局域网地址。

### 8.7 查 Mac 的 IP

```bash
ipconfig getifaddr en0     # Wi-Fi
ipconfig getifaddr en1     # 有线（视机型而定）
```

两个来源对照一下：前端启动日志打印的地址 + 这条命令。换过网络 IP 会变，**以启动日志为准**。

### 8.8 网络怎么接：默认就用 iPhone 的个人热点

**默认就走这条路，不用纠结。**

1. iPhone：「设置 → 个人热点」→ 打开「允许其他人加入」
2. Mac：在 WiFi 里连上你的 iPhone
3. Mac 拿到的 IP 会是 `172.20.10.x`（**通常就是 `172.20.10.2`**，第一台连上的设备）
4. 以 §8.7 的启动日志为准，日志里会有 `on your phone: http://172.20.10.x:8766`

**为什么默认选它：**

- **没有客户端隔离** —— 校园网 / 酒店 / 商场 WiFi 普遍开着这个，设备之间互相不通，
  防火墙放行了也没用。这是「手机打不开」最常见的原因，用热点直接绕开。
- 只有你自己的设备在这个网络里，开着 `HOST=0.0.0.0` 也不会把 demo 暴露给陌生人。
- 不吃场馆 WiFi 的不确定性，现场演示最可控。

**注意：** 用热点期间 iPhone 的「允许其他人加入」要保持开着（息屏没事，
但如果 Mac 断开了要重新连一次）。热点刚连上时 Mac 可能要几秒才拿到 IP，
`ipconfig getifaddr en0` 返回空就等一下再试。

其他接法知道存在就行，不推荐默认用：

| 接法 | Mac 的 IP 长什么样 | 什么时候才用 |
| --- | --- | --- |
| 两者都连同一个家用路由器 | `192.168.x.x` | 在家调试，且路由器没开「AP 隔离」 |
| Mac 有线 + iPhone 连同一路由器 | 和 iPhone 同子网 | 家里网口更快的情况 |
| 都连校园网 / 公司网 / 酒店网 | — | **别用**，大概率被客户端隔离挡住 |

### 8.9 Mac 上的防火墙与权限

- macOS **没有** Windows 那种「入站默认全拒」的机制，**通常不需要手动加放行规则**
- 「系统设置 → 网络 → 防火墙」如果开着可能拦。临时关掉：

  ```bash
  sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate off
  ```

  用完记得开回来（`... --setglobalstate on`），或者把 Node 加进允许列表。
- **「本地网络」权限（macOS 15 Sequoia 起）**：按 Apple 官方文档，**接受入站连接本身不需要**
  这个权限，所以正常情况不会拦你。但如果弹出了
  「允许"终端"查找本地网络中的设备吗?」，**点允许**；误点了「不允许」就去
  「系统设置 → 隐私与安全性 → 本地网络」把 Terminal / iTerm / Node 打开。

### 8.10 iPhone 上打开并装到主屏幕

1. iPhone 连上 8.8 里选定的那个网络
2. **必须用 Safari** —— iOS 上只有 Safari 有「添加到主屏幕」，Chrome 没有这个功能
3. 地址栏输入 `http://<8.7 拿到的 IP>:8766`
4. 点底部分享按钮 → **添加到主屏幕** → 添加
5. 从桌面图标打开 → 全屏、有自己的图标

Safari 打开局域网的 http 地址时，地址栏会显示「不安全」。这是正常的（局域网明文访问），不用管。

> iPhone 侧的权限不用担心：Apple 文档明确写了 **Safari 的流量不需要「本地网络」权限**
> （WKWebView、SFSafariViewController、Safari 都在豁免范围内）。

### 8.11 iPhone 打不开？按这个顺序查

1. **iPhone 真的连在那个网络上吗**——最容易搞错的是 iPhone 其实在蜂窝数据上
2. Mac 上打开 `http://<IP>:8766` 能不能开？**能开** → 说明服务没问题，问题在网络
3. `ipconfig getifaddr en0` 拿到的 IP，和启动日志里的一致吗？（换过网络会变）
4. 换成 **Mac 连 iPhone 热点** 再试（绕开客户端隔离）
5. 关掉 Mac 防火墙再试（见 8.9）
6. 地址别写错：是 `http://` 不是 `https://`，端口 `:8766` 不能漏

### 8.12 用完收尾

1. `.env` 里 `HOST` 改回 `127.0.0.1`（或注释掉），重启前端
2. 两个终端各按 Ctrl+C
3. iPhone 上关掉个人热点

这个 demo **没有任何登录**，只要 `HOST=0.0.0.0` 开着且在用公共网络，
同一个网络的人就能用你的后端和你的模型密钥。所以别长期开着。

### 8.13 Mac + iPhone 下的已知限制

- **离线缓存不生效**：局域网 HTTP 不是安全上下文，`sw.js` 注册不了。
  但「全屏 + 有图标」是通过 manifest 实现的，**照常可用**，演示够用。
- 想要 service worker 真正生效，只有 HTTPS 一条路（ngrok / cloudflared 隧道），
  但那会把没登录的 demo 暴露到公网，**演示场景不推荐**。
- YouTube 相关的失败与平台无关，看第 6 节。

---

## 附：本机已验证的事实（换机器要重新确认）

Windows 机器（本次已验证）：

- 前端端口 `8766`，后端端口 `8000`
- 后端 `127.0.0.1:8000`，前端 `0.0.0.0:8766`（设了 `HOST=0.0.0.0` 时）
- ffmpeg / ffprobe 在 `C:\Users\kevin\.workbuddy\binaries\ffmpeg\bin`
- 已验证版本：Python 3.13.14、Node 22.22.2、ffmpeg 6.0、yt-dlp 2026.08.19

**换网络后局域网 IP 一定会变，以启动日志打印的为准**，
文档里出现的 `172.20.10.2` 只是当时那一次的值。
