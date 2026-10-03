/* 慢慢来 · 双语支持。
 * 约定：zh 是产品原本的声音（一个字都别改），en 是同一套语气的英文。
 * 用法：
 *   <script src="/i18n.js"></script> 放在每页最前面；
 *   静态文案 → data-i18n="key"（textContent）/ data-i18n-html（含 <br>、<span> 的整段）/
 *              data-i18n-ph（placeholder）/ data-i18n-aria（aria-label）；
 *   JS 里的动态文案 → I18N.t("key")，带参数的用 I18N.t("key", {n: 3})；
 *   打接口 → fetch(I18N.api("/api/..."))，英文模式会带上 ?lang=en 让后端一起换语言；
 *   语言切换按钮 → 页面里放 .lang-switch（见 bootLanguageSwitch），i18n.js 负责接线和高亮。
 * 语言存 localStorage("slowly.lang")，?lang=en 可强制并记住。
 */
(function (global) {
  "use strict";

  var DICT = {
    // ---------- 通用 ----------
    "common.brand": { zh: "慢慢来", en: "Slowly" },
    "common.back": { zh: "返回聊天", en: "Back to chat" },
    "common.lang_aria": { zh: "切换语言", en: "Switch language" },
    "common.readjson_404": {
      zh: "接口不存在，请重启前端服务",
      en: "This API is missing — restart the frontend service",
    },
    "common.readjson_bad": {
      zh: "服务返回了无法识别的响应",
      en: "The service returned something unreadable",
    },
    "common.request_failed": { zh: "请求失败", en: "The request failed" },
    "common.no_title": { zh: "（没有标题）", en: "(untitled)" },
    "common.local_video": { zh: "本地视频", en: "Local video" },

    // ---------- 首页（index.html）----------
    "home.title": { zh: "慢慢来 · 你的生活陪做搭子", en: "Slowly · Your buddy for everyday how-tos" },
    "home.aria.menu": { zh: "更多选项", en: "More options" },
    "home.aria.home": { zh: "回到首页", en: "Back to the start" },
    "home.mascot_aria": {
      zh: "抱着小纸心的黄色小慢",
      en: "Slowly, a yellow buddy hugging a little paper heart",
    },
    "home.hello": { zh: "嗨，我是你的小慢", en: "Hi, I'm Slowly" },
    "home.h1_html": {
      zh: "今天想一起<span class=\"underline\">学点什么？</span>",
      en: "What shall we <span class=\"underline\">learn today?</span>",
    },
    "home.sub_html": {
      zh: "把想做的事、看不懂的教程发给我<br>我们按你的节奏，慢慢来。",
      en: "Send me the thing you want to make, or a tutorial you can't follow.<br>We'll take it at your pace, slowly.",
    },
    "home.suggest_head": { zh: "也可以这样问", en: "Or try asking like this" },
    "home.shuffle": { zh: "换一换 ↻", en: "Shuffle ↻" },
    "home.saved_entry": { zh: "存着慢慢做", en: "Saved for later" },
    "home.saved_count": { zh: "{n} 个 · 接着做 →", en: "{n} saved · Continue →" },
    "home.little_note": {
      zh: "一小步，也是一点小小的进步 ♡",
      en: "One small step is still real progress ♡",
    },
    "home.chat_caption": {
      zh: "小慢陪着你 · 按自己的节奏就好",
      en: "Slowly is with you · go at your own pace",
    },
    "home.input_ph": {
      zh: "想学什么，或者在哪一步卡住了？",
      en: "What do you want to learn, or where are you stuck?",
    },
    "home.input_aria": {
      zh: "和小慢说说你想做什么",
      en: "Tell Slowly what you want to make",
    },
    "home.upload": { zh: "上传视频", en: "Upload video" },
    "home.paste_link": { zh: "粘贴链接", en: "Paste a link" },
    "home.send_aria": { zh: "发送消息", en: "Send message" },
    "home.bottom_note": { zh: "AI 陪做 · YouTube 实时检索", en: "AI companion · live YouTube search" },
    "home.desktop_html": {
      zh: "慢慢来 / MOBILE DEMO<br>手机 App · 小程序交互预览",
      en: "Slowly / MOBILE DEMO<br>Mobile app · mini-program preview",
    },
    "home.aria.remove_video": { zh: "移除视频", en: "Remove video" },
    "home.aria.close": { zh: "关闭", en: "Close" },
    "home.preview_aria": {
      zh: "已选择的视频预览",
      en: "Preview of the selected video",
    },
    "home.q1a": {
      zh: "第一次给绿植换盆，要准备些什么？",
      en: "First time repotting a plant — what should I prepare?",
    },
    "home.q1b": {
      zh: "衣服纽扣掉了，能陪我一起缝好吗？",
      en: "A button fell off my coat — can you walk me through sewing it back on?",
    },
    "home.q1c": {
      zh: "这个教程太快了，帮我按步骤慢慢做",
      en: "This tutorial is too fast — help me follow it step by step",
    },
    "home.q2a": {
      zh: "白色衣服沾了污渍，我该从哪一步开始？",
      en: "There's a stain on my white shirt — where do I start?",
    },
    "home.q2b": {
      zh: "想画一张生日贺卡，但我完全没有基础",
      en: "I want to paint a birthday card but I'm a total beginner",
    },
    "home.q2c": {
      zh: "钩针教程看不懂，可以一步步陪我吗？",
      en: "I can't follow this crochet tutorial — can you go through it with me step by step?",
    },
    "home.msg_file": {
      zh: "视频先放在对话里预览。要做成一步步的步骤，从检索结果点「教程分解」。",
      en: "The video stays as a preview in this chat for now. To turn it into steps, tap \"Break down\" on a search result.",
    },
    "home.msg_file_user": {
      zh: "帮我看看这个教程吧",
      en: "Help me with this tutorial, please",
    },
    "home.last_prompt": {
      zh: "我想跟着这个视频学一学",
      en: "I want to follow this video and learn it",
    },
    "home.msg_link": {
      zh: "链接收到了。我不会去读链接里的视频内容。",
      en: "Got the link. I won't read the video behind it.",
    },
    "home.thinking": {
      zh: "小慢正在回答并检索 YouTube…",
      en: "Slowly is thinking and searching YouTube…",
    },
    "home.failed_prefix": { zh: "暂时没能完成回答：", en: "Couldn't finish the reply: " },
    "home.retry": { zh: "重新尝试", en: "Try again" },
    "home.search_none": {
      zh: "YouTube 实时检索没有找到相关教程。",
      en: "The live YouTube search found no matching tutorials.",
    },
    "home.search_head": {
      zh: "YouTube 实时检索 · 点击可在当前页预览原视频",
      en: "Live YouTube search · tap to preview the original video here",
    },
    "home.search_fail_suffix": {
      zh: "，AI 文字回答仍可正常使用。",
      en: " — the text reply still works fine.",
    },
    "home.search_fail_map": {
      zh: "暂时无法连接 YouTube 检索服务",
      en: "Can't reach the YouTube search service right now",
    },
    "home.preview_video": { zh: "预览 YouTube 原视频 →", en: "Preview the original on YouTube →" },
    "home.breakdown_btn": { zh: "教程分解", en: "Break down" },
    "home.creating": { zh: "正在创建任务…", en: "Creating the task…" },
    "home.preview_note": {
      zh: "当前播放的是 YouTube 原视频，尚未读取或解析视频内容。点击“教程分解”后才会开始下载。",
      en: "What's playing is the original YouTube video — nothing has been read or parsed yet. The download only starts when you tap \"Break down\".",
    },
    "home.open_original": {
      zh: "无法播放？打开 YouTube 原视频 ↗",
      en: "Not playing? Open it on YouTube ↗",
    },
    "home.upload_title": { zh: "把教程带过来吧", en: "Bring a tutorial over" },
    "home.upload_sub": {
      zh: "选择相册或文件里的视频，放进对话一起看。",
      en: "Pick a video from your album or files and we'll look at it together.",
    },
    "home.upload_choose": { zh: "↥ 选择本地视频", en: "↥ Choose a local video" },
    "home.upload_privacy": {
      zh: "文件只在当前浏览器里预览，不会上传服务器。",
      en: "The file is previewed in this browser only — nothing is uploaded.",
    },
    "home.upload_bad_type": { zh: "请选择一个视频文件", en: "Please choose a video file" },
    "home.link_title": { zh: "分享你想跟做的教程", en: "Share a tutorial you want to follow" },
    "home.link_sub": {
      zh: "粘贴小红书、TikTok 或其他教程链接。",
      en: "Paste a Xiaohongshu, TikTok or other tutorial link.",
    },
    "home.link_aria": { zh: "教程链接", en: "Tutorial link" },
    "home.link_attach": { zh: "放入聊天框", en: "Put it in the chat box" },
    "home.link_privacy": {
      zh: "链接只是先放进聊天框，我不会去抓取里面的视频。",
      en: "The link just goes into the chat box — I won't fetch the video behind it.",
    },
    "home.link_bad": {
      zh: "请输入以 https:// 或 http:// 开头的完整链接",
      en: "Please enter a full link starting with https:// or http://",
    },
    "home.menu_title": { zh: "留一点时间，慢慢学", en: "Take a little time, learn slowly" },
    "home.menu_saved": { zh: "☆ 存着慢慢做", en: "☆ Saved for later" },
    "home.menu_new": { zh: "＋ 开始新对话", en: "＋ Start a new chat" },
    "home.menu_home": { zh: "⌂ 回到聊天首页", en: "⌂ Back to the start" },
    "home.menu_privacy": {
      zh: "手机 App / 小程序交互原型。聊天只留在当前页面，刷新清空。",
      en: "Mobile app / mini-program interaction prototype. The chat lives on this page only and clears on refresh.",
    },
    "home.saved_none": {
      zh: "还没存下什么。在「一步步做」那一页点一下「存下来」，就会出现在这里。",
      en: "Nothing saved yet. Tap \"Save it\" on a step-by-step page and it'll show up here.",
    },
    "home.saved_hint_none": {
      zh: "还没拆开 · 去看看 →",
      en: "Not broken down yet · Take a look →",
    },
    "home.saved_hint_all": {
      zh: "全部 {n} 步都过了 · 再看一遍 →",
      en: "All {n} steps done · Look again →",
    },
    "home.saved_hint_start": { zh: "共 {n} 步 · 开始 →", en: "{n} steps · Start →" },
    "home.saved_hint_mid": {
      zh: "做到 {done} / {total} 步 · 接着做 →",
      en: "{done} / {total} steps done · Continue →",
    },
    "home.saved_outro": {
      zh: "想移出去，在它的「一步步做」页再点一次「已存下」。",
      en: "To remove one, tap \"Saved ✓\" again on its step-by-step page.",
    },
    "home.saved_fail_prefix": { zh: "读不出来：", en: "Couldn't load: " },
    "home.saved_loading": { zh: "正在读取…", en: "Loading…" },
    "home.saved_cached_note": {
      zh: "先给你看上次拿到的列表（后端这会儿没响应）。",
      en: "Showing the list from last time — the backend isn't responding right now.",
    },
    "home.saved_retry": { zh: "再试一次", en: "Try again" },
    "home.newchat_busy": {
      zh: "请等当前回答完成后再开始新对话",
      en: "Wait for the current reply to finish before starting a new chat",
    },

    // ---------- 步骤页（steps.html）----------
    "steps.title": { zh: "一步步做 · 慢慢来", en: "Step by step · Slowly" },
    "steps.loading_title": { zh: "正在读取教程…", en: "Loading the tutorial…" },
    "steps.loading": { zh: "正在把教程拆成一步步", en: "Breaking the tutorial into steps" },
    "steps.progress_step": { zh: "第 {pos} / {total} 步", en: "Step {pos} of {total}" },
    "steps.progress_all": { zh: "全部过啦 🎉", en: "All steps done 🎉" },
    "steps.done_count": { zh: "已完成 {n} 步", en: "{n} steps done" },
    "steps.save": { zh: "存下来", en: "Save it" },
    "steps.saved": { zh: "已存下 ✓", en: "Saved ✓" },
    "steps.regen": { zh: "重新分解", en: "Redo breakdown" },
    "steps.regen_warn_title": {
      zh: "已经勾了 {n} 步，重拆会清掉",
      en: "{n} steps checked off — redoing clears them",
    },
    "steps.regen_title_plain": { zh: "重新拆一遍", en: "Break it down again" },
    "steps.regen_busy": { zh: "正在重拆…", en: "Redoing…" },
    "steps.regen_note_swap": {
      zh: "正在重新拆，下面的内容一会儿会换掉。",
      en: "Redoing now — the steps below will be swapped out shortly.",
    },
    "steps.chip_done": { zh: "✓ 做到了", en: "✓ Done" },
    "steps.chip_step": { zh: "第 {n} 步", en: "Step {n}" },
    "steps.clip_aria": {
      zh: "这一步在原视频里的那一小段，自动循环播放",
      en: "This step's clip from the original video, looping automatically",
    },
    "steps.frame_alt": {
      zh: "这一步在原视频里的画面",
      en: "This step's frame from the original video",
    },
    "steps.clipbar_aria": {
      zh: "这一小段的进度，点一下可以跳到那一段的任意位置",
      en: "Progress within this clip — click to jump anywhere in it",
    },
    "steps.badge_shots": { zh: "画面切段", en: "Real frame cuts" },
    "steps.badge_even": { zh: "平均分", en: "Even split" },
    "steps.badge_mock": { zh: "通用骨架", en: "Generic skeleton" },
    "steps.badge_sample": { zh: "人工示例", en: "Curated sample" },
    "steps.badge_manual": { zh: "手动加", en: "Added by hand" },
    "steps.badge_model": { zh: "模型看图写的", en: "Written by the vision model" },
    "steps.badge_none": { zh: "标题自己填", en: "Titles filled in as fallback" },
    "steps.badge_fallback": { zh: "步骤", en: "Step" },
    "steps.label_ask_self": { zh: "问自己", en: "Ask yourself" },
    "steps.label_criteria": { zh: "合格标准", en: "Pass criteria" },
    "steps.last_check_prefix": { zh: "小慢上次的判定 · ", en: "Slowly's last verdict · " },
    "steps.last_check_join": { zh: "：", en: ": " },
    "steps.done_btn": { zh: "我做到了", en: "I did it" },
    "steps.done_undo": { zh: "撤销「我做到了」", en: "Undo \"I did it\"" },
    "steps.check_title": { zh: "让小慢看看，这一步过没过", en: "Tell Slowly how it's going" },
    "steps.check_sub": {
      zh: "说清楚你做了什么、现在什么状态，判得越准。",
      en: "Describe what you did and how it looks now — the more precise, the better the verdict.",
    },
    "steps.check_ph": {
      zh: "例如：我把东西都摆到手边了，一共三样，没有中途起身去找。",
      en: "e.g. I laid everything out within reach — three items — and didn't get up mid-way to look for anything.",
    },
    "steps.photo_label": { zh: "＋ 加一张照片（可选）", en: "＋ Add a photo (optional)" },
    "steps.photo_change": { zh: "↻ 换一张照片", en: "↻ Change the photo" },
    "steps.check_btn": { zh: "帮我看看过没过", en: "Did I pass? Take a look" },
    "steps.check_busy": { zh: "小慢正在看…", en: "Slowly is looking…" },
    "steps.check_need_input": {
      zh: "先说两句你现在的状态，或者加一张照片",
      en: "Describe where you are first, or add a photo",
    },
    "steps.check_detail_prefix": { zh: "差在哪：", en: "What's missing: " },
    "steps.verdict_pass": { zh: "这一步过了 ✓", en: "This step passes ✓" },
    "steps.verdict_retry": { zh: "还差一点", en: "Not quite there" },
    "steps.verdict_unclear": { zh: "这次说不清", en: "Can't tell this time" },
    "steps.ask_title": { zh: "卡住了？直接问小慢", en: "Stuck? Ask Slowly directly" },
    "steps.ask_ph": { zh: "这一步的哪里不明白？", en: "What's unclear about this step?" },
    "steps.ask_btn": { zh: "问", en: "Ask" },
    "steps.ask_empty": { zh: "先写一句你的问题", en: "Write your question first" },
    "steps.regen_card_title": { zh: "这份拆分不对？", en: "Is this breakdown off?" },
    "steps.regen_card_sub": {
      zh: "会换掉全部步骤，已勾的进度也一起清掉。",
      en: "It replaces every step and clears the progress you've checked off.",
    },
    "steps.regen_card_btn": { zh: "重新分解这条视频", en: "Redo the breakdown" },
    "steps.empty_invalid": {
      zh: "这个地址里没有有效的任务。",
      en: "This link doesn't point to a valid task.",
    },
    "steps.empty_read_fail": { zh: "暂时读不到步骤：", en: "Couldn't load the steps: " },
    "steps.empty_none": {
      zh: "这条视频没能拆出步骤。",
      en: "No steps could be broken out of this video.",
    },
    "steps.empty_action": { zh: "刷新看看", en: "Refresh" },
    "steps.waiting_fallback": {
      zh: "视频还在下载，下载完我就会按画面把它拆成一步步。",
      en: "The video is still downloading. Once it's here I'll break it into steps from the frames.",
    },
    "steps.toast_saved": {
      zh: "存下来了，想做成的时候回来接着做。",
      en: "Saved. Come back whenever you're ready to actually make it.",
    },
    "steps.toast_unsaved": {
      zh: "已从「存着慢慢做」里拿掉了。",
      en: "Removed from Saved for later.",
    },
    "steps.photo_bad_type": { zh: "请选一张图片", en: "Please pick an image" },
    "steps.photo_too_large": {
      zh: "照片太大了，换一张小一点的",
      en: "That photo is too large — try a smaller one",
    },
    "steps.photo_read_fail": { zh: "照片读取失败", en: "Couldn't read that photo" },
    "steps.photo_bad_decode": {
      zh: "这张图片读不出来，换一张试试",
      en: "Couldn't decode this image — try another one",
    },
    "steps.watch_link": {
      zh: "▶ 在整条视频里看这段 · {range}",
      en: "▶ Watch this part in the full video · {range}",
    },

    // ---------- 视频页（video.html）----------
    "video.title": { zh: "教程视频 · 慢慢来", en: "Tutorial video · Slowly" },
    "video.loading_title": { zh: "正在准备教程视频…", en: "Preparing the tutorial video…" },
    "video.loading_meta": { zh: "正在读取任务信息", en: "Reading the task info" },
    "video.status_pending": { zh: "等待下载", en: "Waiting to download" },
    "video.status_inspecting": { zh: "正在读取视频信息", en: "Reading the video info" },
    "video.status_downloading": { zh: "正在下载", en: "Downloading" },
    "video.status_processing": { zh: "正在合并音视频", en: "Merging audio and video" },
    "video.status_uploading": { zh: "正在保存", en: "Saving" },
    "video.status_ready": { zh: "下载完成", en: "Download complete" },
    "video.status_failed": { zh: "下载失败", en: "Download failed" },
    "video.playing_local": {
      zh: "正在播放后端保存的本地 MP4",
      en: "Playing the local MP4 saved by the backend",
    },
    "video.playing_remote": {
      zh: "下载期间播放 YouTube 原视频",
      en: "Playing the YouTube original while downloading",
    },
    "video.clip_label": {
      zh: "只播 {range} 这一段，播完会停下",
      en: "Playing only {range}, then it stops",
    },
    "video.clip_done": { zh: "这一段播完了 · {range}", en: "This part finished · {range}" },
    "video.open_source": { zh: "打开 YouTube 原视频 ↗", en: "Open the original on YouTube ↗" },
    "video.steps_cta": { zh: "按步骤做 · 一步步来 →", en: "Make it step by step →" },
    "video.note": {
      zh: "下载期间播放 YouTube 原视频；下载完成后会自动切换为后端保存的本地 MP4。请只下载你有权保存的公开视频。",
      en: "The YouTube original plays while downloading; once done it switches to the local MP4 saved by the backend. Only download public videos you have the right to keep.",
    },
    "video.bad_id": { zh: "视频地址无效", en: "Invalid video link" },
    "video.readjson_bad": {
      zh: "视频服务返回了无法识别的响应，请重启前端服务",
      en: "The video service returned something unreadable — restart the frontend service",
    },
    "video.read_fail": { zh: "无法读取视频任务", en: "Couldn't read the video task" },
    "video.youtube_label": { zh: "YouTube 原视频", en: "the original YouTube video" },
  };

  // 后端/代理偶尔会透传一段固定的中文（落库的报错等）。英文模式下按特征翻，
  // 对不上的原样显示——宁可显示中文，也不编一句假的。
  var SERVER_MAP = [
    [/暂时无法连接 YouTube 检索服务/, "Can't reach the YouTube search service right now"],
    [/认为当前网络像机器人/, "YouTube thinks this network looks like a bot and wants a sign-in check. Two options: export cookies from a browser signed into YouTube (Netscape format) and set YT_DLP_COOKIE_FILE in .env, then restart the backend; or try a different network (e.g. your phone's hotspot)."],
    [/年龄限制/, "This video is age-restricted and needs cookies from a YouTube-signed-in account to download (set YT_DLP_COOKIE_FILE in .env)."],
    [/视频看不了/, "YouTube says this video can't be watched (taken down, region-locked or deleted). Try another one."],
    [/私有视频/, "This is a private video — YouTube doesn't allow downloading it. Try a public one."],
    [/会员专享/, "This video is for channel members only; you need that membership's cookies to download it."],
    [/没找到 ffmpeg/, "ffmpeg wasn't found. Install it, point FFMPEG_LOCATION in .env at its bin folder, and restart the backend."],
    [/链接解析不了/, "This link can't be parsed. YouTube links are supported for now — check it's pasted correctly."],
    [/在限流，稍等几分钟/, "YouTube is rate-limiting — wait a few minutes and try again."],
  ];

  var lang = "zh";
  try {
    var stored = global.localStorage.getItem("slowly.lang");
    if (stored === "en" || stored === "zh") lang = stored;
    var forced = new URLSearchParams(global.location.search).get("lang");
    if (forced === "en" || forced === "zh") {
      lang = forced;
      global.localStorage.setItem("slowly.lang", lang);
    }
  } catch (e) { /* 无痕模式等拿不到 localStorage，就用中文 */ }

  function t(key, params) {
    var entry = DICT[key];
    if (!entry) return key;
    var text = entry[lang] || entry.zh || key;
    if (params) {
      Object.keys(params).forEach(function (name) {
        text = text.split("{" + name + "}").join(String(params[name]));
      });
    }
    return text;
  }

  function apply(root) {
    var scope = root || document;
    scope.querySelectorAll("[data-i18n]").forEach(function (node) {
      node.textContent = t(node.getAttribute("data-i18n"));
    });
    scope.querySelectorAll("[data-i18n-html]").forEach(function (node) {
      node.innerHTML = t(node.getAttribute("data-i18n-html"));
    });
    scope.querySelectorAll("[data-i18n-ph]").forEach(function (node) {
      node.setAttribute("placeholder", t(node.getAttribute("data-i18n-ph")));
    });
    scope.querySelectorAll("[data-i18n-aria]").forEach(function (node) {
      node.setAttribute("aria-label", t(node.getAttribute("data-i18n-aria")));
    });
    scope.querySelectorAll("[data-i18n-title]").forEach(function (node) {
      node.setAttribute("title", t(node.getAttribute("data-i18n-title")));
    });
    document.documentElement.lang = lang === "en" ? "en" : "zh-CN";
  }

  // 后端透传的固定中文 → 英文（只对认识的句子，对不上就原样）
  function mapServer(text) {
    if (lang !== "en" || typeof text !== "string") return text;
    for (var i = 0; i < SERVER_MAP.length; i += 1) {
      if (SERVER_MAP[i][0].test(text)) return SERVER_MAP[i][1];
    }
    return text;
  }

  // 接口地址带上语言，后端/代理好一起换文案
  function api(url) {
    if (lang !== "en" || /([?&])lang=/.test(url)) return url;
    return url + (url.indexOf("?") >= 0 ? "&" : "?") + "lang=en";
  }

  function paintSwitch() {
    document.querySelectorAll(".lang-switch button[data-lang]").forEach(function (button) {
      var isOn = button.getAttribute("data-lang") === lang;
      button.classList.toggle("on", isOn);
      button.setAttribute("aria-pressed", isOn ? "true" : "false");
    });
  }

  function setLang(next) {
    if (next !== "en" && next !== "zh") return;
    lang = next;
    try { global.localStorage.setItem("slowly.lang", lang); } catch (e) {}
    apply();
    paintSwitch();
    // 让页面重画动态内容（步骤条、气泡、弹窗……），页面自己监听
    document.dispatchEvent(new CustomEvent("langchange", { detail: { lang: lang } }));
  }

  function bootLanguageSwitch() {
    document.querySelectorAll(".lang-switch button[data-lang]").forEach(function (button) {
      button.addEventListener("click", function () { setLang(button.getAttribute("data-lang")); });
    });
    paintSwitch();
  }

  global.I18N = {
    t: t,
    apply: apply,
    api: api,
    mapServer: mapServer,
    setLang: setLang,
    bootLanguageSwitch: bootLanguageSwitch,
    get lang() { return lang; },
  };
})(window);
