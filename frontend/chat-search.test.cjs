const assert = require("node:assert/strict");
const test = require("node:test");

const { normalizeVideo, searchYoutubeForChat, youtubeQueryFromMessages } = require("./chat-search.cjs");

test("uses the latest user question as the YouTube query", () => {
  const query = youtubeQueryFromMessages([
    { role: "user", content: "我想养绿植" },
    { role: "assistant", content: "是哪一种？" },
    { role: "user", content: "绿萝要怎么换盆？" },
  ]);
  assert.equal(query, "绿萝要怎么换盆？");
});

test("recognizes tutorial requests without a question mark", () => {
  assert.equal(
    youtubeQueryFromMessages([{ role: "user", content: "教我缝纽扣的步骤" }]),
    "教我缝纽扣的步骤",
  );
});

test("does not search links or simple answers", () => {
  assert.equal(youtubeQueryFromMessages([{ role: "user", content: "绿萝" }]), null);
  assert.equal(youtubeQueryFromMessages([{ role: "user", content: "https://example.com/video" }]), null);
});

test("only accepts normalized YouTube search results", () => {
  assert.equal(normalizeVideo({ platform: "bilibili", url: "https://example.com" }), null);
  assert.deepEqual(
    normalizeVideo({
      platform: "youtube",
      platform_video_id: "abc",
      url: "https://www.youtube.com/watch?v=abc",
      title: "绿萝换盆",
      duration_seconds: 123,
    }),
    {
      platform: "youtube",
      platform_video_id: "abc",
      url: "https://www.youtube.com/watch?v=abc",
      title: "绿萝换盆",
      uploader: null,
      duration_seconds: 123,
      thumbnail_url: null,
    },
  );
});

test("calls the FastAPI search endpoint for a question", async () => {
  const originalFetch = global.fetch;
  let requestedUrl = "";
  global.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      json: async () => ({
        cached: false,
        items: [{
          platform: "youtube",
          platform_video_id: "abc",
          url: "https://www.youtube.com/watch?v=abc",
          title: "绿萝换盆教程",
        }],
      }),
    };
  };
  try {
    const result = await searchYoutubeForChat(
      [{ role: "user", content: "绿萝怎么换盆？" }],
      { backendUrl: "http://fastapi.test" },
    );
    assert.match(requestedUrl, /^http:\/\/fastapi\.test\/api\/search\?q=/);
    assert.equal(result.attempted, true);
    assert.equal(result.videos[0].title, "绿萝换盆教程");
  } finally {
    global.fetch = originalFetch;
  }
});
