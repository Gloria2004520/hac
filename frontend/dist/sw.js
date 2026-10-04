// 慢慢来 · CookClip 的 Service Worker
//
// 目标只有一个：现场演示时网络抖一下，页面也能立刻打开。
// 原则：
//   - /api/* 一律不缓存。步骤进度、下载状态、视频流都是实时数据，
//     缓存了就会把「上一次的结果」当成「这一次的结果」，那是在撒谎。
//   - 页面导航用 network-first：有网就拿最新的，断网才退回缓存，
//     这样改了页面不会永远看不到。
//   - 静态资源（i18n.js、图标、manifest）用 stale-while-revalidate：
//     先给缓存秒回，后台悄悄更新。

const VERSION = "v3";
const SHELL_CACHE = `slowly-shell-${VERSION}`;

// 预缓存的应用外壳。改了这里任何一项，都要同步把 VERSION 往上升一位。
const SHELL_ASSETS = [
  "/",
  "/index.html",
  "/video.html",
  "/steps.html",
  "/library.html",
  "/i18n.js",
  "/app-nav.js",
  "/app-nav.css",
  "/manifest.webmanifest",
  "/assets/library/other.png",
  "/assets/library/potato-egg.png",
  "/assets/library/spicy-chicken.png",
  "/assets/library/tools.png",
  "/assets/library/washing-machine.png",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/icons/apple-touch-icon.png",
  "/icons/favicon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // 用 add() 而不是 addAll()：单个资源失败不该让整个离线能力报废
      await Promise.all(
        SHELL_ASSETS.map((asset) =>
          cache
            .add(new Request(asset, { cache: "reload" }))
            .catch(() => {})
        )
      );
      await self.skipWaiting();
    })()
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((key) => key !== SHELL_CACHE).map((key) => caches.delete(key))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  // 只管自己这个源；跨域的缩略图、模型接口一概不碰
  if (url.origin !== self.location.origin) return;
  // 实时数据绝不缓存（也包含视频 Range 流，缓存会让拖动进度条出错）
  if (url.pathname.startsWith("/api/")) return;

  // 页面导航：网络优先，断网退回缓存，缓存里也没有就退回首页
  if (request.mode === "navigate") {
    event.respondWith(
      (async () => {
        try {
          const response = await fetch(request);
          const cache = await caches.open(SHELL_CACHE);
          cache.put(request, response.clone());
          return response;
        } catch {
          const hit = await caches.match(request);
          return hit || (await caches.match("/")) || Response.error();
        }
      })()
    );
    return;
  }

  // 其余静态资源：先给缓存，后台再更新
  event.respondWith(
    (async () => {
      const hit = await caches.match(request);
      const network = fetch(request)
        .then(async (response) => {
          if (response && response.ok) {
            const cache = await caches.open(SHELL_CACHE);
            cache.put(request, response.clone());
          }
          return response;
        })
        .catch(() => hit);
      return hit || (await network);
    })()
  );
});
