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

文字对话的模型接口通过三个变量配置，任何 OpenAI 兼容服务都可以接入：

```bash
MODEL_API_BASE=https://api.deepseek.com/v1   # 默认是 https://openrouter.ai/api/v1
MODEL_API_KEY=sk-xxxxxxxx                    # 对应平台的密钥
MODEL_NAME=deepseek-chat                     # 默认是 OpenRouter 的免费模型
```

接入 DeepSeek 官方 API 时，到 https://platform.deepseek.com 创建密钥，把上面三行填进 `.env`，重启前端即可。

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
