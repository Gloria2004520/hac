"""陪做 / 步骤检查：按某一步的 checkpoint 判定「过了没有」，或者回答卡住时的问题。

诚实底线（和前端一致）：
    模型没有看过这个视频，它只能根据「步骤上下文 + 用户自己的描述」来判断。
    所以提示词里明确禁止编造画面、时间戳和专有名词；判不了就说不清（unclear），
    不许安慰式放行。

降级顺序：有模型 → 模型判定；没模型/模型挂了 → 不装懂，给一条明确的引导，
并把 basis 标成 none / fallback，让前端如实显示。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings

VERDICTS = ("pass", "retry", "unclear")

# 免费/小模型经常不老实输出英文枚举值，统一收一下
_VERDICT_ALIASES = {
    "pass": "pass",
    "passed": "pass",
    "ok": "pass",
    "通过": "pass",
    "过了": "pass",
    "做到了": "pass",
    "retry": "retry",
    "fail": "retry",
    "failed": "retry",
    "不通过": "retry",
    "没过": "retry",
    "还没过": "retry",
    "重做": "retry",
    "unclear": "unclear",
    "unknown": "unclear",
    "说不清": "unclear",
    "不确定": "unclear",
}


class ModelError(RuntimeError):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def model_ready() -> bool:
    return bool(settings.model_key)


def model_label() -> str:
    return f"{settings.model_name} @ {settings.model_endpoint}"


def chat(
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 800,
    temperature: float = 0.3,
    model: str | None = None,
) -> str:
    """调一次 OpenAI 兼容的 chat/completions，返回正文。失败一律抛 ModelError。"""
    key = settings.model_key
    if not key:
        raise ModelError("服务端还没配置模型密钥", status=503)

    try:
        response = httpx.post(
            f"{settings.model_endpoint}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model or settings.model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False,
            },
            timeout=settings.model_timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise ModelError("模型响应超时，稍后再试一次", status=504) from exc
    except httpx.HTTPError as exc:
        raise ModelError("连不上模型服务，请检查网络或接口地址", status=502) from exc

    if response.status_code != 200:
        raise ModelError(_provider_message(response), status=502 if response.status_code != 429 else 429)

    try:
        payload = response.json()
    except ValueError as exc:
        raise ModelError("模型返回了无法识别的响应", status=502) from exc

    choices = payload.get("choices") or []
    content = (choices[0].get("message") or {}).get("content") if choices else None
    if isinstance(content, list):  # 少数接口按分段返回
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not content or not str(content).strip():
        raise ModelError("模型没有返回内容", status=502)
    return str(content).strip()


def _provider_message(response: httpx.Response) -> str:
    shared_pool = False
    try:
        failure = response.json()
        shared_pool = (
            (failure.get("error") or {}).get("metadata", {}).get("limit_source")
            == "upstream_provider_shared_pool"
        )
    except ValueError:
        pass

    if response.status_code == 429:
        return (
            "免费模型的上游共享额度池正在限流，暂时没法判定。请稍后再试；这不是你的输入问题。"
            if shared_pool
            else "模型请求受限（429），请稍后再试。"
        )
    if response.status_code in (401, 402, 403):
        return f"模型服务拒绝了这次请求（{response.status_code}），请检查密钥、余额和模型名称。"
    return f"模型服务返回 {response.status_code}，请检查密钥权限、余额和模型名称。"


_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)

# 陪做这块自己的界面文案。zh 必须和改造前一字不差。
_T: dict[str, dict[str, str]] = {
    "no_model_reason": {
        "zh": "我这边还没配模型密钥，没办法替你判定。先照着下面的合格标准自己过一遍，有拿不准的地方直接问我。",
        "en": "I don't have a model key configured yet, so I can't judge this for you. Go through the pass criteria below yourself, and ask me about anything you're unsure of.",
    },
    "no_model_note": {
        "zh": "没接模型，这条只是引导，不是判定。",
        "en": "No model attached — this is guidance, not a verdict.",
    },
    "check_failed_reason": {
        "zh": "这次没能判定：{error}",
        "en": "Couldn't judge this time: {error}",
    },
    "check_failed_note": {
        "zh": "模型没调通，别把这条当结论。",
        "en": "The model call didn't go through — don't treat this as a verdict.",
    },
    "bad_format_reason": {
        "zh": "模型这次没按格式回答，我没法判定。你可以把你的做法再说具体一点，比如「用了多少、看到什么颜色、什么状态」。",
        "en": "The model didn't answer in the expected format, so I can't judge. Try describing what you did more concretely — how much you used, what colour you saw, what state it's in.",
    },
    "bad_format_note": {
        "zh": "模型回复格式不完整，这条不算判定。",
        "en": "The model's reply was incomplete — this doesn't count as a verdict.",
    },
    "no_reason": {"zh": "模型没有给理由。", "en": "The model gave no reason."},
    "image_note_used": {"zh": "模型看了你发的照片。", "en": "The model looked at the photo you sent."},
    "image_note_failed": {
        "zh": "这次的模型没能读你的照片，判定只基于你写的文字。",
        "en": "This model couldn't read your photo; the verdict is based on your text only.",
    },
    "image_note_disabled": {
        "zh": "照片只留给你自己对照（配置里关掉了发图），判定只基于你写的文字。",
        "en": "The photo is just for your own reference (sending images is off in the config); the verdict is based on your text only.",
    },
    "check_note_suffix": {
        "zh": "模型没看过这个视频，判定依据是合格标准和你自己的描述。",
        "en": "The model hasn't watched this video; the verdict is based on the pass criteria and your own description.",
    },
    "no_model_answer": {
        "zh": "关于「{title}」这一步，判断标准是：{criteria}我这边还没配模型密钥，只能给你标准，你先对着它看一遍。",
        "en": "For the step \"{title}\", the pass criteria are: {criteria}I don't have a model key configured yet, so all I can give you is the criteria — check yourself against it.",
    },
    "no_model_answer_note": {
        "zh": "没接模型，这条用的是步骤自带的合格标准，不是模型回答。",
        "en": "No model attached — this is the step's own pass criteria, not a model answer.",
    },
    "ask_failed_answer": {
        "zh": "这次没能回答：{error}你先照着合格标准对一遍，或者再问我一次。",
        "en": "Couldn't answer this time: {error} Check yourself against the pass criteria, or ask me again.",
    },
    "ask_failed_note": {"zh": "模型没调通。", "en": "The model call didn't go through."},
    "ask_note": {
        "zh": "模型写的，记得自己核对。",
        "en": "Written by the model — double-check it yourself.",
    },
}


def _t(key: str, lang: str) -> str:
    table = _T.get(key)
    if not table:
        return key
    return table.get("en" if lang == "en" else "zh") or table["zh"]


def parse_loose_json(text: str) -> dict[str, Any] | None:
    """从模型的自由输出里挖一个 JSON 对象出来。免费模型经常包着解释文字或代码围栏。"""
    if not text:
        return None
    stripped = _JSON_FENCE.sub("", text.strip()).strip()

    candidates: list[str] = [stripped]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
        if isinstance(data, str):  # 有些模型会把 JSON 再套一层字符串
            try:
                inner = json.loads(data)
            except ValueError:
                continue
            if isinstance(inner, dict):
                return inner
    return None


def _normalize_verdict(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return _VERDICT_ALIASES.get(value.strip().lower())


@dataclass
class CheckOutcome:
    verdict: str
    reason: str
    detail: str
    basis: str  # model | fallback | none
    note: str = ""
    model_name: str | None = None


CHECK_SYSTEM = "\n".join(
    [
        "你是「慢慢来」的步骤检查助手。用户正跟着一份带步骤的教程做，现在停在某一步，把现场情况描述给你，请你判断「这一步过了没有」。",
        "判断依据只有三样：这一步要做什么、用户要回答的自检问题、合格标准。",
        "你没有看过这个视频，所以绝对不许编造视频里的画面、时间戳、食材、品牌、数字或任何专有信息。",
        "规则：",
        "- 用户的描述能对上合格标准 → verdict=\"pass\"；",
        "- 明显还差关键动作/关键量/关键状态，或用户自己说没做完 → verdict=\"retry\"；",
        "- 描述太模糊、答非所问、信息不足以判断 → verdict=\"unclear\"，并在 reason 里用一句反问把最必要的信息要回来。",
        "不要安慰式放行：说不清就说不清。也不要因为用户语气不确定就直接判重做。",
        "只输出 JSON，不要代码围栏，不要解释：",
        '{"verdict":"pass|retry|unclear","reason":"2~3句，用「你」称呼，说清为什么","detail":"retry 时写清差的到底是什么；pass/unclear 给空字符串"}',
    ]
)

# 英文界面的同一套规矩。判定标准一个字都不能松：没有看过的画面就是不能编。
CHECK_SYSTEM_EN = "\n".join(
    [
        'You are the step checker for "Slowly". The user is following a step-by-step tutorial and has stopped at one step; they describe their situation and you judge whether this step is done.',
        "Judge only from three things: what this step asks for, the self-check question, and the pass criteria.",
        "You have NOT watched the video, so you must never invent footage, timestamps, ingredients, brands, numbers or any specifics from it.",
        "Rules:",
        '- The description matches the pass criteria → verdict="pass";',
        '- A key action/amount/state is clearly missing, or the user says it isn\'t finished → verdict="retry";',
        '- Too vague, off-topic, or not enough information → verdict="unclear", and ask back for the single most necessary detail in `reason`.',
        "Never pass someone out of kindness: if you can't tell, say unclear. Don't fail them just for sounding unsure either.",
        "Always reply to the user in English. Output JSON only, no code fences, no explanations:",
        '{"verdict":"pass|retry|unclear","reason":"2-3 sentences addressed to the user, saying why","detail":"when retry, what exactly is missing; empty string for pass/unclear"}',
    ]
)


def _step_context(step: Any) -> str:
    return "\n".join(
        [
            f"这一步：{step.title}",
            f"这一步要做什么：{step.summary}",
            f"用户要回答的自检问题：{step.question}",
            f"合格标准：{step.criteria}",
            f"卡住时的提示：{step.hint}" if getattr(step, "hint", None) else "",
        ]
    ).strip()


def _fallback(reason: str, note: str, basis: str = "fallback") -> CheckOutcome:
    return CheckOutcome(
        verdict="unclear",
        reason=reason,
        detail="",
        basis=basis,
        note=note,
        model_name=None,
    )


def check_step(
    step: Any,
    report: str,
    image_data_url: str | None = None,
    *,
    lang: str = "zh",
) -> CheckOutcome:
    """判定一步过没过。永远返回结果，不抛异常——模型挂了也要给用户一句实话。"""
    lang = "en" if lang == "en" else "zh"
    system = CHECK_SYSTEM_EN if lang == "en" else CHECK_SYSTEM
    if not model_ready():
        return _fallback(_t("no_model_reason", lang), _t("no_model_note", lang), basis="none")

    wants_image = bool(image_data_url) and settings.model_vision_enabled
    text_only = f"{_step_context(step)}\n\n用户自己描述的现场情况：{report}"

    def with_image_messages() -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": text_only},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]

    def text_only_messages() -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": text_only},
        ]

    used_image = wants_image
    try:
        raw = chat(
            with_image_messages() if wants_image else text_only_messages(),
            max_tokens=500,
            temperature=0.2,
            model=settings.vision_model if wants_image else None,
        )
    except ModelError as exc:
        # 有些模型收不了图会直接 400。退一步：只拿文字再判一次，别让整条判定白跑。
        if wants_image and exc.status == 400:
            used_image = False
            try:
                raw = chat(text_only_messages(), max_tokens=500, temperature=0.2)
            except ModelError as retry_exc:
                return _fallback(
                    _t("check_failed_reason", lang).format(error=retry_exc),
                    _t("check_failed_note", lang),
                )
        else:
            return _fallback(
                _t("check_failed_reason", lang).format(error=exc),
                _t("check_failed_note", lang),
            )

    if not image_data_url:
        image_note = ""
    elif used_image:
        image_note = _t("image_note_used", lang)
    elif settings.model_vision_enabled:
        image_note = _t("image_note_failed", lang)
    else:
        image_note = _t("image_note_disabled", lang)

    parsed = parse_loose_json(raw)
    verdict = _normalize_verdict(parsed.get("verdict") if parsed else None)
    if parsed is None or verdict is None:
        return _fallback(_t("bad_format_reason", lang), _t("bad_format_note", lang))

    reason = str(parsed.get("reason") or "").strip() or _t("no_reason", lang)
    detail = str(parsed.get("detail") or "").strip()

    note = image_note + _t("check_note_suffix", lang)
    return CheckOutcome(
        verdict=verdict,
        reason=reason,
        detail=detail if verdict == "retry" else "",
        basis="model",
        note=note,
        model_name=settings.vision_model if used_image else settings.model_name,
    )


ASK_SYSTEM = "\n".join(
    [
        "你是「慢慢来」的陪做教练。用户正跟着一份带步骤的教程做，现在在某一卡住了，问你一个问题。",
        "用简体中文，口语化、简短，通常 2~4 句，直接给「可执行的动作」或「可判定的现象」，不要复述整份教程。",
        "你没有看过这个视频，也没听过它的讲解，所以不要编造视频里的画面、时间戳、专有名词或数字。",
        "不确定的时候要说「不确定」，或者反问一个最必要的问题。不要输出代码围栏，不要用列表堆砌。",
    ]
)

ASK_SYSTEM_EN = "\n".join(
    [
        'You are the coaching buddy of "Slowly". The user is following a step-by-step tutorial, is stuck at one step, and asks you a question.',
        "Reply in English, conversational and short — usually 2-4 sentences. Give an actionable move or an observable check, not a recap of the whole tutorial.",
        "You have NOT watched the video and have not heard its narration, so never invent footage, timestamps, proper nouns or numbers from it.",
        "Say you're not sure when you aren't, or ask back the single most necessary question. No code fences, no bullet lists.",
    ]
)


def ask_step(step: Any, question: str, *, lang: str = "zh") -> dict[str, Any]:
    """卡住时问一句。返回 {answer, basis, note, model_name}。"""
    lang = "en" if lang == "en" else "zh"
    system = ASK_SYSTEM_EN if lang == "en" else ASK_SYSTEM
    if not model_ready():
        return {
            "answer": _t("no_model_answer", lang).format(
                title=step.title, criteria=step.criteria
            ),
            "basis": "none",
            "note": _t("no_model_answer_note", lang),
            "model_name": None,
        }

    try:
        answer = chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"{_step_context(step)}\n\n用户的问题：{question}"},
            ],
            max_tokens=500,
            temperature=0.4,
        )
    except ModelError as exc:
        return {
            "answer": _t("ask_failed_answer", lang).format(error=exc),
            "basis": "none",
            "note": _t("ask_failed_note", lang),
            "model_name": None,
        }

    return {
        "answer": answer,
        "basis": "model",
        "note": _t("ask_note", lang),
        "model_name": settings.model_name,
    }
