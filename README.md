# 慢慢来 · CookClip

教程陪做与视频素材整理的原型项目：前端是 Node 服务，后端是 FastAPI 检索与视频落库服务。

## 目录结构

```text
.
├── .env.example           前后端共用的配置模板
├── requirements.txt       后端 Python 依赖
├── frontend/              前端：Node 服务 + 静态页面
│   ├── server.cjs         静态页面、文字对话、检索聚合、步骤/视频代理
│   ├── chat-search.cjs    调用后端 /api/search
│   ├── chat-search.test.cjs
│   └── dist/
│       ├── index.html     “慢慢来”手机 App 风格页面
│       ├── video.html     单条视频页（下载进度 + 本地播放）
│       └── steps.html     一步步做（步骤 + 代表画面 + 判定 + 问答）
└── backend/               后端：FastAPI 视频落库服务（CookClip）
    ├── app/               应用源码
    │   ├── video_analysis.py  ffprobe/ffmpeg 封装：读时长、找画面切点、抽帧
    │   ├── breakdown.py       把视频拆成带 checkpoint 的步骤（真拆 / 骨架）
    │   └── coach.py          步骤判定、卡住时的问答
    └── tests/             单元测试
```

## 配置

前端和后端共用仓库根目录的同一个 `.env`：

```bash
cp .env.example .env    # 填入自己的模型密钥，勿提交密钥
```

`frontend/server.cjs` 读取 `../.env`，`backend/app/config.py` 读取仓库根目录的 `.env`，两边都会忽略与自己无关的配置项。

文字对话默认使用 OpenRouter 的免费模型，在 `.env` 里填上密钥即可：

```bash
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx    # 默认免费模型必填；勿提交密钥
```

### 切换到 DeepSeek

想改用 DeepSeek 官方 API（按你账号的用量计费），先到 https://platform.deepseek.com 创建一个 API Key，然后编辑 `.env`：

```bash
MODEL_API_BASE=https://api.deepseek.com/v1
MODEL_API_KEY=sk-你的 DeepSeek 密钥
MODEL_NAME=deepseek-chat                # 推理模型用 deepseek-reasoner
```

保存后重启前端（`cd frontend && node server.cjs`）生效。想切回 OpenRouter 免费模型，把 `MODEL_API_BASE` 改成 `https://openrouter.ai/api/v1`、`MODEL_NAME` 改成 `inclusionai/ling-3.0-flash-sante:free`，并确保 `OPENROUTER_API_KEY` 已填写。

三个变量的规则：`MODEL_API_KEY` 优先于 `OPENROUTER_API_KEY`；`MODEL_API_BASE` 和 `MODEL_NAME` 不填时用代码里的默认值（OpenRouter 免费模型）。

## 步骤是怎么拆出来的

视频下载完成后，`backend/app/breakdown.py` 会做一次真分解，结果落在 `tutorial_steps` /
`tutorial_breakdowns` 两张表里，代表画面落在 `backend/data/storage/frames/<视频 id>/<分解 id>/`。

链路只有两步，都是能拿出证据的：

1. **找画面切点** —— `ffmpeg -vf "select='gt(scene,0.2)',metadata=mode=print:key=lavfi.scene_score:file=-"`
   一趟解码拿到所有画面变化点和分数，再由 `pick_cuts()` 按分数挑边界（两段至少隔 8 秒、最多切 10 段）。
   画面几乎不变时退回按总时长平均分，并把 `basis` 标成 `even`。
2. **让模型看截图** —— 每段取中间那一帧缩成小 JPEG，逐段发给视觉模型，让它写标题、说明、自检问题和合格标准。

   提示词（`breakdown.CAPTION_SYSTEM`）刻意往「做菜的话」上拧，而不是「描述画面」：
   标题必须是动作指令（「把洋葱顺着纹路切成细丝」），说明要说清这一步要达成什么、为什么，
   并**明确禁止**用「画面中/图中/这一帧」开头。认得出的食材就直说，认不出的才说「这块食材」，
   不许写成「白色块状物」。数字、品牌、人名，以及「视频里说…」这类话一律不许编。

**刻意没有做的事**：没有语音转写（没接 ASR）、没有 OCR、没有目标检测。模型只看到每段的**一张截图**，
所以界面上写的是「这一帧里有什么」，不是「这一段讲了什么」。所有步骤都带两个诚实标记：

| 字段 | 取值 | 含义 |
| --- | --- | --- |
| `basis` | `shots` | 段边界来自真实画面切换 |
| | `even` | 画面几乎没变化，按总时长平均分 |
| | `mock` | 通用骨架，一个字都没读这个视频（拆失败时的兜底） |
| `text_basis` | `model` | 标题/说明/标准是模型看这一段截图写的 |
| | `none` | 没人写，只留了画面，标题要用户自己看 |

相关接口：

```text
GET    /api/videos/{id}/steps                      拿步骤（首次访问会起一个后台分解）
POST   /api/videos/{id}/steps/regenerate[?force=1] 重新分解（后台跑，立刻返回；有进度时必须带 force=1）
GET    /api/videos/{id}/steps/{step_id}/frame      这一步的代表画面（JPEG）
PATCH  /api/videos/{id}/steps/{step_id}            勾「我做到了」/ 留备注
POST   /api/videos/{id}/steps/{step_id}/check      判定这一步过没过
POST   /api/videos/{id}/steps/{step_id}/ask        卡住时问一句
```

分解在后台线程里跑，`GET /steps` 会返回 `analyzing: true`，页面轮询等它变成 `false`——不要在这里同步跑，
不然页面会卡住半分钟。失败的分解会被记成 `status="failed"` 并退回骨架，但**不会**每次刷新都自动重试，
避免反复白烧 ffmpeg；要重来请用「重新分解」。

## 启动后端

需要 Python 3.12 与 FFmpeg（macOS 可用 `brew install ffmpeg`）。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload --port 8000   # http://localhost:8000
```

Windows 上 ffmpeg 不在 PATH 里时，把 `FFMPEG_LOCATION` 指到它的 `bin` 目录即可（yt-dlp 合并音视频
和步骤分解都要用）。后端会在 `backend/data/` 下自动创建 SQLite 库、视频素材库与 `frames/` 代表画面目录，
该目录不入库。FastAPI 不再提供独立的 CookClip 网页；`http://127.0.0.1:8000/docs` 保留为接口文档。

## 启动前端

需要 Node.js 18 或更新版本，无需安装依赖。

```bash
cd frontend && node server.cjs    # http://127.0.0.1:8766/
```

## 原型限制

聊天中的教程问题会调用 FastAPI 在 YouTube 实时检索。点击结果会在当前聊天页弹窗播放 YouTube 原视频；点击播放器右下角的“教程分解”后才开始下载并进入独立页面。下载期间继续播放原视频，完成后自动切换本地 MP4。

步骤分解是**真的**（画面切点 + 视觉模型看代表帧），但它只看截图、没听声音、没有字幕转写，
所以模型写的是「这一帧里有什么」而不是「这一段讲了什么」；画面里烧进去的字幕它看得见，视频的讲解内容它不知道。
界面上每一步都标了这一段的边界和文字各是从哪来的。检索、下载和判定都会如实报告失败，不会把失败说成“没搜到”。
免费模型可能受限流影响。

两个服务都只监听本机地址；部署为公开服务前需添加用户认证、请求限额及服务端密钥管理。
