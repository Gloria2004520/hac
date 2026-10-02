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
│   ├── tutorial.cjs       字幕/文字生成结构化 SOP（仅免费模型）
│   ├── dist/tutorial.js   SOP 查看、编辑、参考帧提取与导入导出
│   └── dist/index.html    “慢慢来”手机 App 风格页面
└── backend/               后端：FastAPI 视频落库服务（CookClip）
    ├── app/               应用源码
    └── tests/             单元测试
```

## 配置

前端和后端共用仓库根目录的同一个 `.env`：

```bash
cp .env.example .env    # 填入自己的 OpenRouter 密钥，勿提交密钥
```

`frontend/server.cjs` 读取 `../.env`，`backend/app/config.py` 读取仓库根目录的 `.env`，两边都会忽略与自己无关的配置项。

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

聊天中的教程问题会调用 FastAPI 在 YouTube 实时检索。点击结果会在当前聊天页弹窗播放 YouTube 原视频；点击播放器右下角的“教程分解”后才开始下载并进入独立页面。下载期间继续播放原视频，完成后自动切换本地 MP4。检索和下载不代表 AI 已观看视频。免费模型可能受限流影响。

## 视频拆解（dev/fyh）

视频页下方提供分步骤 SOP：工具清单（必需/可选、用量、替代备注）、动作说明、完成标准、易错点、补救建议和静态安全提示。不包含打卡、执行进度或新手实时引导。

1. 下载完成后，点击“从视频字幕生成 SOP”。后端按需提取中文/英文字幕并缓存，前端调用现有免费文字模型整理草稿，不发起付费或自动重试请求。
2. 没有字幕、平台限制或字幕过长时，可粘贴教程讲解文字（20～20000 字）生成。失败会显示原因，不会用示例伪装解析结果。
3. 字幕步骤引用原文与真实时间点。点击“回看”跳转原片；点击“提取字幕时间点画面”从本地视频截取参考帧，也可手动暂停后为每步保存更合适的画面。
4. 可编辑工具、步骤顺序、操作和提示，导出/导入 JSON。草稿和参考帧保存在当前浏览器；清除浏览器数据会丢失本地草稿，请用导出保存。

首页“体验教程拆解”可打开 `/video.html?demo=button` 的人工编写缝纽扣示例，不请求模型。示例无关联视频，画面不会凭空生成。

**能力边界：** 当前为字幕/文字驱动的 SOP 整理，尚未接入视觉分析、音频转写或关键画面语义识别。字幕可能识别错误，参考帧不保证对应最佳动作。操作引用与 AI 补充提示均有来源说明，用户编辑后会标明。安全提示仅供核对，不表示自动安全检查通过。原聊天页的本地视频上传仍仅供预览。

新增接口：`POST /api/tutorial` 接收 `{ "videoId": "视频任务ID" }` 或 `{ "text": "教程文字" }`，返回 `{ "tutorial": { ... } }`；后端 `POST /api/videos/{id}/transcript` 返回带时间点的字幕片段。

验证（使用模拟字幕/模型，不消耗模型额度）：

```bash
node --test frontend/chat-search.test.cjs frontend/tutorial.test.cjs
# 后端依赖之外，接口测试需要 pip install httpx
(cd backend && python -m unittest discover -s tests)
# 可选：安装 playwright，并启动本地前端后运行浏览器验证
DEMO_URL=http://127.0.0.1:8766 node frontend/tutorial.browser.cjs # 在仓库根目录运行
```

两个服务都只监听本机地址；部署为公开服务前需添加用户认证、请求限额及服务端密钥管理。
