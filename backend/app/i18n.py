"""按请求语言（zh/en）取界面文案。

约定：
- 中文是产品原本的声音，zh 的每个值必须和改造前的字面完全一致（有测试盯着）。
- en 只出现在 `?lang=en` 的请求里；没传就永远走 zh，老客户端零感知。
- 只放「会原样显示给用户」的短句；模型生成的内容（步骤卡、陪聊回答）不走这里。
"""

from __future__ import annotations

from typing import Literal

Lang = Literal["zh", "en"]

STRINGS: dict[str, dict[str, str]] = {
    # ---- 步骤页的临时说明（_steps_response，每次请求现算，不落库）----
    "note.reanalyzing_skeleton": {
        "zh": "下面这几步还是通用骨架。我正在按真实画面重新拆，一会儿会自动换掉，不用刷新。",
        "en": "These steps are still the generic skeleton. I'm re-breaking the video down from the real frames and will swap them in automatically — no need to refresh.",
    },
    "note.analyzing": {
        "zh": "正在看画面。我会用 ffmpeg 找出画面真正切换的地方，再让看图的模型挨段看截图，可能要半分钟。",
        "en": "Watching the frames now. I use ffmpeg to find where the picture actually cuts, then a vision model reads each segment's key frame — this can take about half a minute.",
    },
    "note.waiting": {
        "zh": "视频还在下载。下载完我会自动按画面把它拆成一步步，到时候刷新这一页就行。",
        "en": "The video is still downloading. Once it's here I'll break it into steps from the frames automatically — just refresh this page then.",
    },
    # ---- 步骤相关接口的报错 ----
    "error.video_not_found": {"zh": "任务不存在", "en": "This task doesn't exist"},
    "error.video_not_ready": {
        "zh": "视频尚未准备完成",
        "en": "The video isn't ready yet",
    },
    "error.video_still_processing": {
        "zh": "视频仍在处理中，请完成后再删除",
        "en": "The video is still being processed — delete it once it finishes",
    },
    "error.step_not_found": {"zh": "这一步不存在", "en": "This step doesn't exist"},
    "error.no_frame": {
        "zh": "这一步没有留下代表画面",
        "en": "This step has no representative frame",
    },
    "error.frame_path_bad": {
        "zh": "代表画面的路径不对",
        "en": "The frame path is invalid",
    },
    "error.frame_missing": {
        "zh": "代表画面的文件不在了",
        "en": "The frame file is gone",
    },
    "error.frame_read_failed": {
        "zh": "代表画面读取失败",
        "en": "Failed to read the frame",
    },
    "error.photo_format": {
        "zh": "照片格式不对，只接受 data:image/... 开头的图片",
        "en": "That photo format isn't supported — send a data:image/... URL",
    },
    "error.photo_too_large": {
        "zh": "照片太大了，换一张小一点的",
        "en": "That photo is too large — try a smaller one",
    },
    "error.cannot_regen_not_local": {
        "zh": "这条视频还没下载到本地，没法重拆。",
        "en": "This video isn't downloaded locally yet, so it can't be re-broken down.",
    },
    "error.regen_would_reset": {
        "zh": "你已经做到了 {done} 步。重新分解会换掉全部步骤，这些勾和判定记录都会清掉。确认的话带上 force=1 再来一次。",
        "en": "You've already checked off {done} step(s). Breaking it down again replaces every step, and those check marks and verdicts will be cleared. Pass force=1 to confirm.",
    },
    "error.queue_unavailable": {
        "zh": "本地任务队列暂不可用，稍后再试",
        "en": "The local job queue is unavailable right now — try again shortly",
    },
    "error.queue_unavailable_analysis": {
        "zh": "本地任务队列暂不可用，稍后再试",
        "en": "The local job queue is unavailable right now — try again shortly",
    },
    "error.image_required": {
        "zh": "图片内容不能为空",
        "en": "Image content is required",
    },
    # ---- 检索 ----
    "error.search_empty": {
        "zh": "请输入要搜索的菜名",
        "en": "Type something to search for first",
    },
    "error.search_timeout": {
        "zh": "检索超时，可稍后重试或直接粘贴视频链接",
        "en": "The search timed out — try again, or paste a video link directly",
    },
}

# 允许的取值，别的一律当 zh 处理
SUPPORTED = ("zh", "en")


def normalize(lang: str | None) -> Lang:
    return "en" if lang == "en" else "zh"


def msg(key: str, lang: str | None) -> str:
    """取一句。缺 key / 缺语言时退回中文，宁可显示中文也不显示 key。"""
    table = STRINGS.get(key)
    if not table:
        return key
    return table.get(normalize(lang)) or table["zh"]
