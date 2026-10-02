const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

function youtubeQueryFromMessages(messages) {
  const latest = [...messages].reverse().find((message) => message.role === "user");
  if (!latest || typeof latest.content !== "string") return null;

  const text = latest.content.replace(/https?:\/\/\S+/gi, " ").replace(/\s+/g, " ").trim();
  if (!text) return null;

  const looksLikeQuestion = /[?？]/.test(text);
  const asksForTutorial = /(怎么|怎样|如何|什么|哪|能不能|可以吗|怎么办|为什么|是否|有没有|想学|教我|帮我|教程|步骤|准备)/i.test(text);
  if (!looksLikeQuestion && !asksForTutorial) return null;
  return text.slice(0, 50);
}

function normalizeVideo(item) {
  if (!item || item.platform !== "youtube" || typeof item.url !== "string") return null;
  if (!/^https:\/\/(www\.)?youtube\.com\/watch\?/i.test(item.url)) return null;
  return {
    platform: "youtube",
    platform_video_id: String(item.platform_video_id || ""),
    url: item.url,
    title: String(item.title || "未命名视频").slice(0, 500),
    uploader: item.uploader ? String(item.uploader).slice(0, 300) : null,
    duration_seconds: Number.isFinite(item.duration_seconds) ? item.duration_seconds : null,
    thumbnail_url: typeof item.thumbnail_url === "string" ? item.thumbnail_url : null,
  };
}

async function searchYoutubeForChat(messages, options = {}) {
  const query = youtubeQueryFromMessages(messages);
  if (!query) return { attempted: false, query: null, cached: false, videos: [], error: null };

  const backendUrl = (options.backendUrl || process.env.VIDEO_BACKEND_URL || DEFAULT_BACKEND_URL).replace(/\/$/, "");
  try {
    const response = await fetch(`${backendUrl}/api/search?q=${encodeURIComponent(query)}`, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(options.timeoutMs || 12_000),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || `视频检索服务返回 ${response.status}`);
    const videos = Array.isArray(data.items)
      ? data.items.map(normalizeVideo).filter(Boolean).slice(0, 4)
      : [];
    return { attempted: true, query, cached: Boolean(data.cached), videos, error: null };
  } catch (error) {
    console.error("YouTube search failed:", error.message);
    return { attempted: true, query, cached: false, videos: [], error: "暂时无法连接 YouTube 检索服务" };
  }
}

module.exports = { normalizeVideo, searchYoutubeForChat, youtubeQueryFromMessages };
