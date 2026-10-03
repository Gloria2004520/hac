"""分解：把一段素材变成「带 checkpoint 的步骤」。

三条路，每条都必须如实标注，绝不能混着说：

    真分解（这条视频已经下载到本地了）
        · ffmpeg 找到真实画面切点 → 段边界                basis="shots"
        · 视觉模型看每段的代表帧 → 标题/说明/自检/标准     text_basis="model"
        · 画面几乎没变化、切不出段 → 按总时长平均分        basis="even"

    没素材（还没下载完、文件丢了、ffmpeg 不可用）
        · 通用骨架，一个字都没读视频                      basis="mock"

无论走哪条路，都不做的事：
    ✗ 没有语音转写（没接 ASR），所以不知道视频里讲了什么
    ✗ 没有 OCR、没有目标检测
    ✓ 模型只看得到每段的**一张截图**，不是整段视频，也没有声音

所以模型写的标题、说明、合格标准，一律只能说成「看着这一帧猜的」。
这句话必须原样出现在给用户看的说明里（见 real_note / mock_note）。
"""

from __future__ import annotations

import base64
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app import video_analysis
from app.coach import ModelError, chat, model_label, parse_loose_json
from app.config import settings

MOCK_BASIS = "mock"
SHOT_BASIS = "shots"
EVEN_BASIS = "even"

MODEL_TEXT = "model"
NO_TEXT = "none"

# 最多切几段：代表帧要逐段发给模型，段数多了又慢又贵
MAX_SEGMENTS = video_analysis.MAX_SEGMENTS
# 切不出真实边界时的兜底段数
EVEN_FALLBACK_SEGMENTS = 6
# 同时问几段。免费模型单次不快，串行会等到天荒地老
CAPTION_CONCURRENCY = 3


# ---------------------------------------------------------------- mock（没素材）


# 通用骨架：刻意不写任何「视频里出现过的东西」——没有食材、没有品牌、没有数字。
# 每一步都配一个自检问题 + 一条可判定的合格标准，这样「过了没有」才有意义。
SKELETON: list[dict[str, str]] = [
    {
        "title": "先弄清这一步要准备什么",
        "summary": "开工前把手边的东西备齐。这一步不产生成品，但决定了后面会不会反复停下来找东西。",
        "question": "你要用到的东西，是不是都已经在手边了？",
        "criteria": "能一口气说清这一步要用的全部材料/工具，不用中途起身去找。",
        "hint": "先把要用的东西摆出来拍一张照，缺什么一眼就能看出来。",
    },
    {
        "title": "对齐「做完该是什么样」",
        "summary": "先想清楚这一步的完成画面，再动手。没有完成标准，做完了也不知道对不对。",
        "question": "这一步做完时，你眼前应该出现什么样子？",
        "criteria": "能用一句话说出一个「可以用眼睛确认」的状态，而不是「做好了」。",
        "hint": "把这一步的最后一帧定格，用它当进入下一步的入场券。",
    },
    {
        "title": "抓住最敏感的那个量",
        "summary": "一步通常只有一个量最要命：时间、温度、用量或次数。先把它找出来。",
        "question": "这一步最不能出错的那个数字是多少？",
        "criteria": "能指出一个具体数值，并说出它偏大或偏小会带来什么后果。",
        "hint": "找不到数字就先问自己：这一步做久了会怎样？量少了会怎样？",
    },
    {
        "title": "动手，然后停下来对一遍",
        "summary": "做完不要立刻进下一步。停十秒，把自己的状态和合格标准对一遍。",
        "question": "你现在这里，和合格标准里的样子差在哪？",
        "criteria": "能指出至少一处差异；确实没有差异，也要能明确说出「没有」。",
        "hint": "差异说不出来，通常不是真没问题，而是标准还没写具体。",
    },
    {
        "title": "把状态固定住，别拖累下一步",
        "summary": "有些步骤的全部价值，就是让下一步能顺利开始——比如降温、静置、擦干净、收口。",
        "question": "如果这一步没做到位，下一步会以什么形式露出来？",
        "criteria": "能说出一条「下一步的异常现象」，并说清它和这一步的因果关系。",
        "hint": "错误很少在本步现身，通常要到下一步的失败里才看得出来。",
    },
    {
        "title": "留一句「我做了什么」",
        "summary": "用一句话记下用量、时间和结果。下次想复现，靠的就是这句话。",
        "question": "用一句话说清你刚做了什么、用了多少、花了多久。",
        "criteria": "这句话过一天再看，你还能照着它复现出来。",
        "hint": "发现记不清，往往说明这一步里有个量你当时没留意。",
    },
]


def build_steps(video: Any | None) -> list[dict[str, Any]]:
    """没素材时的通用骨架（不含 video_id）。

    video 只用来做两件事：拿总时长算占位时间点；其余一概不读。
    """
    duration = getattr(video, "duration_seconds", None)
    duration = float(duration) if duration else None
    count = len(SKELETON)

    drafts: list[dict[str, Any]] = []
    for index, item in enumerate(SKELETON):
        drafts.append(
            {
                "position": index,
                "title": f"第 {index + 1} 步 · {item['title']}",
                "summary": item["summary"],
                "question": item["question"],
                "criteria": item["criteria"],
                "hint": item["hint"],
                # 时间点只是按总时长平均分的占位，不是真正的步骤边界
                "start_seconds": round(index * duration / count, 1) if duration else None,
                "end_seconds": round((index + 1) * duration / count, 1) if duration else None,
                "basis": MOCK_BASIS,
                "text_basis": NO_TEXT,
                "frame_key": None,
            }
        )
    return drafts


def mock_note(video: Any | None) -> str:
    """给用户看的诚实说明。前端原样展示，不要删、不要美化。"""
    parts = [
        "这份步骤是模拟的（mock）：我们没有读画面、没有转写字幕、也没有抽帧，"
        "给你的是一套通用的骨架。",
        "所以别把它当成这个视频的解析结果——每一步的标题和内容，都要对着画面自己改。",
    ]
    if getattr(video, "duration_seconds", None):
        parts.append("时间点只是按视频总时长平均分出来的占位，不是真正的步骤边界。")
    else:
        parts.append("这条任务还没读到总时长，所以连占位时间点都没有。")
    return "".join(parts)


# ---------------------------------------------------------------- 真分解


@dataclass
class Segment:
    """真分析出来的一段。frame 是这一段的代表画面（小 JPEG）。"""

    position: int
    start_seconds: float
    end_seconds: float
    frame: bytes
    title: str
    summary: str
    question: str
    criteria: str
    hint: str | None
    text_basis: str  # model | none


@dataclass
class Breakdown:
    """一次真分解的完整结果。落库前不碰数据库，方便单测。"""

    method: str  # shots | even | mock
    duration: float
    width: int | None
    height: int | None
    cuts: list[float]
    segments: list[Segment] = field(default_factory=list)
    model_name: str | None = None
    # 段数统计，用来写诚实说明
    captioned: int = 0
    uncaptioned: int = 0
    note: str = ""

    @property
    def basis(self) -> str:
        return self.method

    def drafts(self) -> list[dict[str, Any]]:
        """转成可直接落库的步骤草稿（不含 video_id / breakdown_id / frame_key）。"""
        drafts: list[dict[str, Any]] = []
        for segment in self.segments:
            drafts.append(
                {
                    "position": segment.position,
                    "title": segment.title,
                    "summary": segment.summary,
                    "question": segment.question,
                    "criteria": segment.criteria,
                    "hint": segment.hint,
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "basis": self.method,
                    "text_basis": segment.text_basis,
                }
            )
        return drafts


CAPTION_SYSTEM = "\n".join(
    [
        "你是「慢慢来」的陪做助手，在帮一个厨房新手把一段视频拆成能照着做的步骤。",
        "下面给你其中一段的一张代表画面。你要写的**不是「这张图里有什么」**，"
        "而是「看到这一段的人，手上该做什么、要往哪儿看、做到什么程度算好」。",
        "",
        "怎么说话（这条最重要）：",
        "- 像站在旁边搭把手的人，用「你」，短句，大白话。",
        "- **不许**用「画面中」「图中」「这一帧」「可以看到」开头，那是机器话，不是做菜的话。",
        "- 标题写成一句动作指令，像菜谱上的一行，例如「把洋葱顺着纹路切成细丝」。"
        "能认出来是什么就直接说（洋葱、黄瓜、芹菜、西兰花…）；真认不出的才说「这块食材」，"
        "别写「白色块状物」这种没人会这么说的词。",
        "- 说明写一到两句：先说这一步要达成什么，再说为什么（比如厚薄一致下锅才熟得匀）。"
        "别去复述画面上摆了什么东西、什么颜色、什么材质。",
        "- 自检问题是这一步做完后，你能用一句话回答的问题。",
        "- 合格标准必须是「用眼睛看一眼就能确认的状态」，不许写「做好了」「差不多」「适当」。",
        "",
        "什么能说什么不能说：",
        "- 具体到数字的东西（几克、几度、几分钟、几成油温）、品牌名、人名，"
        "以及「视频里说…」「讲解提到…」这种话，一律不许编。",
        "- 通用厨艺常识可以说一点，但要说得保守、留有余地，不能讲得像原视频下的定论。",
        "- 这一帧如果是片头、标题字幕、有人出镜讲话或者空镜，标题就如实写「开场介绍」「出镜讲解」，"
        "不要硬凑成一步操作。",
        "",
        "只输出 JSON，不要代码围栏，不要任何解释：",
        '{"title":"动作指令，不超过 14 个字","summary":"一到两句大白话","question":"做完能自问自答的一句话","criteria":"用眼睛能确认的状态"}',
    ]
)

# 英文请求（?lang=en）下直接让视觉模型写英文卡片，省掉一次中文→英文的二次翻译。
# 诚实规则逐条对应中文版，一个都不能少。
CAPTION_SYSTEM_EN = "\n".join(
    [
        "You are Slowly's hands-on companion, helping a kitchen beginner break one segment of a video into a step they can follow.",
        "Below is one key frame from that segment. What you write is **not** \"what's in this picture\" — it's what someone watching this segment should do with their hands, where to look, and how to tell it's done.",
        "",
        "Voice (this matters most):",
        "- Talk like a person standing next to them, use \"you\", short sentences, plain words.",
        "- **Never** start with \"In the image\", \"This frame shows\", \"You can see\" — that's machine talk, not coaching talk.",
        "- The title is one action instruction, like a line in a recipe, e.g. \"Slice the onion into thin strips along the grain\". "
        "If you can tell what it is, name it (onion, cucumber, celery, broccoli…); only say \"this ingredient\" when you truly can't tell — "
        "never write things nobody says like \"the white block\".",
        "- The summary is one or two sentences: what this step is trying to achieve, then why (e.g. even thickness so it cooks evenly). "
        "Don't recite what objects are on screen, their colors or materials.",
        "- The question is one question the user can answer in a sentence after doing this step.",
        "- The pass criteria must be a state you can confirm **with one look** — never \"done well\", \"about right\", \"as appropriate\".",
        "",
        "What you may and may not say:",
        "- Never invent specific numbers (grams, degrees, minutes, oil temperature), brand names, people's names, "
        "or phrases like \"the video says…\" / \"the host mentions…\".",
        "- General kitchen common sense is allowed, but keep it conservative and hedged, never stated as the video's conclusion.",
        "- If this frame is an intro, a title card, someone talking to camera, or an empty shot, honestly title it \"Opening intro\" / \"On-camera explanation\" — don't force it into an action step.",
        "",
        "Output JSON only, no code fences, no explanations:",
        '{"title":"action instruction, max 12 words","summary":"one or two plain sentences","question":"one self-check question","criteria":"a state you can confirm by looking"}',
    ]
)


def _data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def _clean_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    text = " ".join(text.split())
    return text[:limit]


# 模型偶尔还是会把「第 3 步 · 」写进标题里，我们自己会加前缀，所以先剥掉
_TITLE_PREFIX = re.compile(r"^\s*第\s*\d+\s*步\s*[·:：\-—]?\s*")


def _clean_title(value: Any, limit: int = 40) -> str:
    return _TITLE_PREFIX.sub("", _clean_text(value, limit)).strip().strip("「」\"'")


def caption_segment(segment: Segment, total: int, duration: float, lang: str = "zh") -> Segment:
    """让视觉模型看一眼这一段的代表帧，把卡片文字填进去。

    永远不抛异常：模型没答上来就返回 text_basis="none"，
    让调用方如实告诉用户「这一段只有画面，标题要你自己看」。
    lang="en" 时直接让模型写英文（存进 en_* 逻辑由调用方负责，这里只管生成语言）。
    """
    if not settings.model_key or not settings.model_vision_enabled:
        segment.text_basis = NO_TEXT
        return segment

    english = lang == "en"
    if english:
        prompt = (
            f"This video is {duration:.0f} seconds long and I split it into {total} segments by picture changes.\n"
            f"This is segment {segment.position + 1} (original video {segment.start_seconds:.0f}–{segment.end_seconds:.0f} s), its key frame attached.\n"
            "Following the rules above, write a companion card for this segment in English."
        )
    else:
        prompt = (
            f"这段视频总长 {duration:.0f} 秒，我按画面变化把它切成了 {total} 段。\n"
            f"这是第 {segment.position + 1} 段（原视频 {segment.start_seconds:.0f}~{segment.end_seconds:.0f} 秒）"
            "的代表画面。\n"
            "照上面的要求，给这一段写一张陪做卡片。"
        )
    try:
        raw = chat(
            [
                {"role": "system", "content": CAPTION_SYSTEM_EN if english else CAPTION_SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": _data_url(segment.frame)}},
                    ],
                },
            ],
            max_tokens=600,
            temperature=0.2,
            model=settings.vision_model,
        )
    except ModelError:
        segment.text_basis = NO_TEXT
        return segment

    parsed = parse_loose_json(raw)
    if not parsed:
        segment.text_basis = NO_TEXT
        return segment

    title = _clean_title(parsed.get("title"))
    summary = _clean_text(parsed.get("summary"), 200)
    question = _clean_text(parsed.get("question"), 120)
    criteria = _clean_text(parsed.get("criteria"), 200)
    if not (title and summary and question and criteria):
        # 缺任何一项就没法判定了，宁可退回「只有画面」
        segment.text_basis = NO_TEXT
        return segment

    prefix = f"Step {segment.position + 1} · " if english else f"第 {segment.position + 1} 步 · "
    segment.title = f"{prefix}{title}"
    segment.summary = summary
    segment.question = question
    segment.criteria = criteria
    # 页面上已经不显示 hint 了，提示词也不再要它
    segment.hint = None
    segment.text_basis = MODEL_TEXT
    return segment


def _placeholder_text(position: int, start: float, end: float, lang: str = "zh") -> tuple[str, str, str, str, str | None]:
    """没有模型时，只给「这一段是真实画面切出来的」这个事实，绝不编内容。"""
    if lang == "en":
        return (
            f"Step {position + 1} · The picture cuts to a new segment here",
            f"This segment boundary comes from the picture itself ({start:.0f}–{end:.0f} s), but no vision model was "
            "available this time, so I can't tell what it's doing yet. Look at the screenshot above and write down what this step is.",
            "Looking at this screenshot, can you say what this step is doing?",
            "The description you wrote yourself matches what's in the screenshot.",
            "Pause on the screenshot first and say in one sentence what's happening in the picture, then move on.",
        )
    return (
        f"第 {position + 1} 步 · 画面切到新的这一段",
        f"这一段是画面自己切出来的（{start:.0f}~{end:.0f} 秒），但这次没有能看图的模型，"
        "所以我还不知道它在做什么。看看上面的截图，把这一步在做什么写下来。",
        "你看着这张截图，能说出这一步在做什么吗？",
        "你自己写的那句描述，能对得上截图里的画面。",
        "先把截图暂停，用一句话说出画面里正在发生的事，再往下走。",
    )


def _blank_segment(position: int, start: float, end: float, frame: bytes, lang: str = "zh") -> Segment:
    title, summary, question, criteria, hint = _placeholder_text(position, start, end, lang)
    return Segment(
        position=position,
        start_seconds=start,
        end_seconds=end,
        frame=frame,
        title=title,
        summary=summary,
        question=question,
        criteria=criteria,
        hint=hint,
        text_basis=NO_TEXT,
    )


def real_note(breakdown: Breakdown) -> str:
    """真分解的诚实说明。前端原样展示，一个字都别删。"""
    parts: list[str] = []

    if breakdown.method == SHOT_BASIS:
        parts.append(
            f"这次是真拆的：我用 ffmpeg 找出画面真正切换的地方（{len(breakdown.cuts)} 个切点，"
            f"切成 {len(breakdown.segments)} 段），再让看图的模型挨段看代表画面，写下标题和合格标准。"
        )
    else:
        parts.append(
            f"这条视频的画面几乎没什么变化，切不出真实的步骤边界，所以我按总时长平均分了 "
            f"{len(breakdown.segments)} 段。这个边界是我分的，不是画面切出来的。"
        )

    if breakdown.captioned:
        parts.append(
            "要说清楚：模型只看得到每段的一张截图，不是整段视频，也没听声音。"
            "所以它写的是「这一帧里有什么」——画面里烧进去的字幕它看得见（那本来就画在图上），"
            "但视频讲了什么、为什么这么做，它不知道。抄进脑子里之前先对着画面核一遍。"
        )
    if breakdown.uncaptioned:
        parts.append(
            f"其中 {breakdown.uncaptioned} 段模型没答上来，只留了截图，标题要你自己看着画面填。"
        )
    if not breakdown.captioned:
        parts.append("这次没有可用的看图模型，所以我只给出真实的画面切点和每段截图，内容一个字都没编。")
    return "".join(parts)


def real_note_en(record) -> str:
    """英文版诚实说明。与 real_note 同源同数据，英文请求（?lang=en）下用这份。

    record 是落库后的 TutorialBreakdown 行（method/cuts_json/segment_count/
    captioned_count/frame_count 都在），说明只按真实数据生成，一个字都不编。
    """
    import json as _json

    try:
        cuts = _json.loads(record.cuts_json or "[]")
    except ValueError:
        cuts = []
    captioned = record.captioned_count
    uncaptioned = max(record.segment_count - captioned, 0)
    parts: list[str] = []

    if record.method == SHOT_BASIS:
        parts.append(
            f"This is a real breakdown: ffmpeg found where the picture actually cuts "
            f"({len(cuts)} cuts, {record.segment_count} segments), then a vision model read "
            f"each segment's key frame and wrote the titles and pass criteria. "
        )
    else:
        parts.append(
            f"This video barely changes on screen, so no real step boundaries could be detected — "
            f"I split it evenly by total duration into {record.segment_count} segments. "
            f"The boundaries are mine, not cut from the picture. "
        )

    if captioned:
        parts.append(
            "To be clear: the model only sees one screenshot per segment, not the whole segment, "
            "and it never hears the audio. So it writes \"what's in this frame\" — burned-in "
            "subtitles are visible (they're painted onto the picture), but what the video says or "
            "why it does things this way is unknown. Check it against the picture before you take "
            "it as fact. "
        )
    if uncaptioned:
        parts.append(
            f"For {uncaptioned} of those segments the model had no answer, so they only keep a "
            f"screenshot — the title is yours to fill in from the picture. "
        )
    if not captioned:
        parts.append(
            "No vision model was available this time, so I only give the real cut points and each "
            "segment's screenshot — nothing is made up."
        )
    return "".join(parts)


def analyze(
    video_path: Path,
    *,
    on_step: Any | None = None,
    lang: str = "zh",
) -> Breakdown:
    """对本地视频做一次真分解。失败一律抛 video_analysis.AnalysisError / OSError。

    流程：ffprobe 读时长 → ffmpeg 找画面切点 → 定段边界 → 逐段抽代表帧 → 模型看图写卡片。
    lang="en" 时模型直接写英文卡片（?lang=en 的「重新分解」就不需要二次翻译了）。
    """
    info = video_analysis.probe_video(video_path)

    scenes = video_analysis.detect_scenes(video_path)
    cuts = video_analysis.pick_cuts(scenes, info.duration)

    if cuts:
        method = SHOT_BASIS
        boundaries = video_analysis.split_boundaries(cuts, info.duration)
    else:
        # 画面几乎不变（固定机位、纯口播、静态演示）。这时不说「切不出来还不说」，
        # 而是退回平均分，并把 method 标成 even。
        method = EVEN_BASIS
        boundaries = video_analysis.even_boundaries(info.duration, EVEN_FALLBACK_SEGMENTS)

    breakdown = Breakdown(
        method=method,
        duration=info.duration,
        width=info.width,
        height=info.height,
        cuts=cuts,
    )

    for index in range(len(boundaries) - 1):
        start, end = boundaries[index], boundaries[index + 1]
        at = video_analysis.frame_sample_time(start, end)
        frame = video_analysis.extract_frame(video_path, at)
        breakdown.segments.append(_blank_segment(index, start, end, frame, lang))
        if on_step:
            on_step(index + 1, len(boundaries) - 1)

    if settings.model_key and settings.model_vision_enabled:
        total = len(breakdown.segments)
        duration = breakdown.duration
        with ThreadPoolExecutor(max_workers=CAPTION_CONCURRENCY) as pool:
            breakdown.segments = list(
                pool.map(
                    lambda segment: caption_segment(segment, total, duration, lang),
                    breakdown.segments,
                )
            )
        breakdown.model_name = model_label()

    breakdown.captioned = sum(1 for item in breakdown.segments if item.text_basis == MODEL_TEXT)
    breakdown.uncaptioned = len(breakdown.segments) - breakdown.captioned
    breakdown.note = real_note(breakdown)
    return breakdown
