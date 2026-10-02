# 慢慢来 · CookClip

教程陪做与视频素材整理的原型项目：前端是 Node 服务，后端是 FastAPI 检索与视频落库服务。

## 目录结构

```text
.
├── .env.example           前后端共用的配置模板
├── requirements.txt       后端 Python 依赖
├── frontend/              前端：Node 服务 + 静态页面
│   ├── server.cjs         静态页面、文字对话、检索聚合
│   ├── chat-search.cjs    调用后端 /api/search
│   ├── chat-search.test.cjs
│   └── dist/index.html    “慢慢来”手机 App 风格页面
└── backend/               后端：FastAPI 视频落库服务（CookClip）
    ├── app/               应用源码
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

## 启动后端

需要 Python 3.12 与 FFmpeg（macOS 可用 `brew install ffmpeg`）。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && uvicorn app.main:app --reload --port 8000   # http://localhost:8000
```

后端会在 `backend/data/` 下自动创建 SQLite 库与视频素材库，该目录不入库。
FastAPI 不再提供独立的 CookClip 网页；`http://127.0.0.1:8000/docs` 保留为接口文档。

## 启动前端

需要 Node.js 18 或更新版本，无需安装依赖。

```bash
cd frontend && node server.cjs    # http://127.0.0.1:8766/
```

## 原型限制

聊天中的教程问题会调用 FastAPI 在 YouTube 实时检索。点击结果会在当前聊天页弹窗播放 YouTube 原视频；点击播放器右下角的“教程分解”后才开始下载并进入独立页面。下载期间继续播放原视频，完成后自动切换本地 MP4。检索和下载不代表 AI 已观看或解析视频；视频步骤解析尚未接入。免费模型可能受限流影响。

两个服务都只监听本机地址；部署为公开服务前需添加用户认证、请求限额及服务端密钥管理。
