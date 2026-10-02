const http = require("node:http");
const fs = require("node:fs");
const path = require("node:path");
const { Readable } = require("node:stream");
const { searchYoutubeForChat } = require("./chat-search.cjs");

const root = __dirname;
const envPath = path.join(root, "..", ".env");
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, "utf8").split("\n")) {
    const at = line.indexOf("=");
    if (at > 0 && !process.env[line.slice(0, at)]) {
      process.env[line.slice(0, at)] = line.slice(at + 1).trim();
    }
  }
}

const videoBackendUrl = (process.env.VIDEO_BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const port = Number.parseInt(process.env.PORT || "8766", 10);
// 对话模型配置：默认使用 OpenRouter 免费模型，任何 OpenAI 兼容接口都可以用环境变量替换
const modelApiBase = (process.env.MODEL_API_BASE || "https://openrouter.ai/api/v1").replace(/\/+$/, "");
const modelApiKey = process.env.MODEL_API_KEY || process.env.OPENROUTER_API_KEY || "";
const modelName = process.env.MODEL_NAME || "inclusionai/ling-3.0-flash-sante:free";

function requestIsSameOrigin(req) {
  return !req.headers.origin || req.headers.origin === `http://${req.headers.host}`;
}

async function readBody(req, limit = 30_000) {
  let raw = "";
  for await (const chunk of req) {
    raw += chunk;
    if (raw.length > limit) throw Object.assign(new Error("请求内容过大"), { status: 413 });
  }
  return raw;
}

async function proxyJson(res, apiPath, options = {}) {
  try {
    const upstream = await fetch(`${videoBackendUrl}${apiPath}`, {
      ...options,
      headers: { Accept: "application/json", ...(options.headers || {}) },
      signal: AbortSignal.timeout(15_000),
    });
    const body = await upstream.text();
    res.writeHead(upstream.status, {
      "Content-Type": upstream.headers.get("content-type") || "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    });
    return res.end(body);
  } catch (error) {
    console.error("Video backend request failed:", error.message);
    return reply(res, 502, { error: "暂时无法连接视频下载服务" });
  }
}

async function proxyVideoContent(req, res, videoId) {
  try {
    const headers = {};
    if (req.headers.range) headers.Range = req.headers.range;
    const upstream = await fetch(`${videoBackendUrl}/api/videos/${videoId}/content`, { headers });
    const responseHeaders = { "Cache-Control": "private, max-age=3600" };
    for (const name of ["content-type", "content-length", "content-range", "accept-ranges"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders[name] = value;
    }
    res.writeHead(upstream.status, responseHeaders);
    if (!upstream.body) return res.end();
    return Readable.fromWeb(upstream.body).pipe(res);
  } catch (error) {
    console.error("Video content proxy failed:", error.message);
    return reply(res, 502, { error: "暂时无法读取已下载的视频" });
  }
}

const system = `你是“慢慢来”，温暖、简洁的日常教程陪做助手。用简体中文。首先识别用户的具体对象和真实意图，不要一上来按教程详细程度分类。比如“第一次给绿植换盆”，先问是哪种植物，列举绿萝/龟背竹、多肉/仙人掌、兰花等实际品类；允许用户不知道品种。已知品种后再确认换盆原因和当前状态。每轮只问一个最必要的问题，不要一次列举大量问题、分类或答案。等待用户自由输入后继续。回复通常控制在2至4句，用户明确要求步骤时才展开详细内容。不重复问已知信息。澄清充分后按材料、具体操作、完成标准、可能错误和补救提供指导。聊天服务会另外展示 YouTube 实时检索得到的标题和链接；这些结果不是你检索或看过的。你不能观看、解析用户上传的视频或检索结果，绝不能声称看过视频、了解原片内容或编造时间戳。用户要求直接给步骤时可给通用指导，但标明不是视频解析。遇到未知材料/植物时不要作确定性判断。只返回直接给用户看的中文正文，不要输出 JSON、字段名或代码围栏。`;

function parseReply(content) {
  let text = content.trim().replace(/^\x60{3}(?:json)?\s*/i, "").replace(/\s*\x60{3}$/, "");
  for (let i = 0; i < 3; i += 1) {
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed === "string") {
        text = parsed;
        continue;
      }
      if (parsed && typeof parsed.message === "string") {
        text = parsed.message;
        continue;
      }
      return null;
    } catch {
      break;
    }
  }
  if (/^\s*\{/.test(text) || /^\s*\x60{3}/.test(text)) return null;
  return { message: text, options: [] };
}

async function requestModel(messages) {
  const upstream = await fetch(`${modelApiBase}/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${modelApiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: modelName,
      messages: [{ role: "system", content: system }, ...messages],
      max_tokens: 900,
      temperature: 0.4,
      stream: false,
    }),
    signal: AbortSignal.timeout(55_000),
  });
  if (!upstream.ok) {
    let providerFailure = {};
    try {
      providerFailure = await upstream.json();
    } catch {}
    const sharedPool = providerFailure.error?.metadata?.limit_source === "upstream_provider_shared_pool";
    console.error("Provider HTTP", upstream.status, "shared_pool", sharedPool);
    const message = upstream.status === 429
      ? (sharedPool
        ? "免费模型的上游共享额度池正在限流，暂时无法生成回复。请稍后再试；这不是你的输入问题。"
        : "模型请求受限（429），请稍后再试。")
      : `模型服务返回 ${upstream.status}，请检查密钥权限、余额和模型名称。`;
    const error = new Error(message);
    error.status = upstream.status === 429 ? 429 : 502;
    throw error;
  }
  const data = await upstream.json();
  const content = data.choices?.[0]?.message?.content;
  if (!content) throw new Error("模型未返回内容");
  const result = parseReply(content);
  if (!result) throw new Error("模型回复格式不完整，请重试。");
  return result;
}

let busy = false;
const reply = (res, status, data) => {
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(JSON.stringify(data));
};

http.createServer(async (req, res) => {
  if (req.method === "POST" && req.url === "/api/chat") {
    if (!requestIsSameOrigin(req)) {
      return reply(res, 403, { error: "不允许跨站请求" });
    }
    if (busy) return reply(res, 429, { error: "上一条还在回答，请稍等" });

    let raw = "";
    try {
      raw = await readBody(req, 60_000);
      const body = JSON.parse(raw);
      if (!Array.isArray(body.messages) || !body.messages.length) throw new Error("输入格式不正确");
      const messages = body.messages.slice(-12).map((message) => {
        if (!["user", "assistant"].includes(message.role)
          || typeof message.content !== "string"
          || message.content.length > 6000) {
          throw new Error("消息格式或长度不正确");
        }
        return { role: message.role, content: message.content };
      });
      if (!modelApiKey) return reply(res, 503, { error: "服务端尚未配置密钥" });

      busy = true;
      const [modelResult, searchResult] = await Promise.all([
        requestModel(messages),
        searchYoutubeForChat(messages),
      ]);
      return reply(res, 200, {
        message: modelResult.message,
        options: Array.isArray(modelResult.options)
          ? modelResult.options.filter((value) => typeof value === "string").slice(0, 4)
          : [],
        videos: searchResult.videos,
        video_search: {
          attempted: searchResult.attempted,
          query: searchResult.query,
          cached: searchResult.cached,
          error: searchResult.error,
        },
      });
    } catch (error) {
      return reply(res, error.status || 502, {
        error: error.name === "TimeoutError"
          ? "回答超时，请重新发送。"
          : (error.message || "请求失败，请稍后重试。"),
      });
    } finally {
      busy = false;
    }
  }

  if (req.method === "POST" && req.url === "/api/videos") {
    if (!requestIsSameOrigin(req)) return reply(res, 403, { error: "不允许跨站请求" });
    try {
      const raw = await readBody(req);
      JSON.parse(raw);
      return proxyJson(res, "/api/videos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: raw,
      });
    } catch (error) {
      return reply(res, error.status || 400, { error: error.message || "请求格式不正确" });
    }
  }

  const pathname = req.url.split("?")[0];
  const videoMatch = pathname.match(/^\/api\/videos\/([A-Za-z0-9-]{1,64})$/);
  if (req.method === "GET" && videoMatch) {
    return proxyJson(res, `/api/videos/${videoMatch[1]}`);
  }
  const contentMatch = pathname.match(/^\/api\/videos\/([A-Za-z0-9-]{1,64})\/content$/);
  if (req.method === "GET" && contentMatch) {
    return proxyVideoContent(req, res, contentMatch[1]);
  }

  if (req.method !== "GET" || !["/", "/index.html", "/video.html", "/vedio.html"].includes(pathname)) {
    res.writeHead(404);
    return res.end("Not found");
  }
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  });
  const filename = ["/video.html", "/vedio.html"].includes(pathname) ? "video.html" : "index.html";
  return fs.createReadStream(path.join(root, "dist", filename)).pipe(res);
}).listen(port, "127.0.0.1", () => console.log(`Local demo: http://127.0.0.1:${port}`));
