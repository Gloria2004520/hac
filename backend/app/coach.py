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


def check_step(step: Any, report: str, image_data_url: str | None = None) -> CheckOutcome:
    """判定一步过没过。永远返回结果，不抛异常——模型挂了也要给用户一句实话。"""
    if not model_ready():
        return _fallback(
            "我这边还没配模型密钥，没办法替你判定。先照着下面的合格标准自己过一遍，"
            "有拿不准的地方直接问我。",
            "没接模型，这条只是引导，不是判定。",
            basis="none",
        )

    vision_model = settings.model_vision_name if image_data_url else None
    used_image = bool(vision_model)

    user_text = f"{_step_context(step)}\n\n用户自己描述的现场情况：{report}"
    if image_data_url and not used_image:
        user_text += "\n（用户还带了照片，但这个模型看不了图片，请只根据上面这段文字判断。）"

    if used_image:
        user_content: Any = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": image_data_url}},
        ]
    else:
        user_content = user_text

    try:
        raw = chat(
            [
                {"role": "system", "content": CHECK_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=500,
            temperature=0.2,
            model=vision_model,
        )
    except ModelError as exc:
        return _fallback(
            f"这次没能判定：{exc}", "模型没调通，别把这条当结论。"
        )

    parsed = parse_loose_json(raw)
    verdict = _normalize_verdict(parsed.get("verdict") if parsed else None)
    if parsed is None or verdict is None:
        return _fallback(
            "模型这次没按格式回答，我没法判定。你可以把你的做法再说具体一点，比如「用了多少、看到什么颜色、什么状态」。",
            "模型回复格式不完整，这条不算判定。",
        )

    reason = str(parsed.get("reason") or "").strip() or "模型没有给理由。"
    detail = str(parsed.get("detail") or "").strip()

    notes = []
    if used_image:
        notes.append("模型看了你发的照片。")
    elif image_data_url:
        notes.append("照片只发给你自己对照，这个模型看不了图，判定只基于你的文字描述。")
    notes.append("模型没看过这个视频，判定依据是合格标准和你自己的描述。")

    return CheckOutcome(
        verdict=verdict,
        reason=reason,
        detail=detail if verdict == "retry" else "",
        basis="model",
        note="".join(notes),
        model_name=vision_model or settings.model_name,
    )


ASK_SYSTEM = "\n".join(
    [
        "你是「慢慢来」的陪做教练。用户正跟着一份带步骤的教程做，现在在某一卡住了，问你一个问题。",
        "用简体中文，口语化、简短，通常 2~4 句，直接给「可执行的动作」或「可判定的现象」，不要复述整份教程。",
        "你没有看过这个视频，也没听过它的讲解，所以不要编造视频里的画面、时间戳、专有名词或数字。",
        "不确定的时候要说「不确定」，或者反问一个最必要的问题。不要输出代码围栏，不要用列表堆砌。",
    ]
)


def ask_step(step: Any, question: str) -> dict[str, Any]:
    """卡住时问一句。返回 {answer, basis, note, model_name}。"""
    if not model_ready():
        return {
            "answer": (
                f"关于「{step.title}」这一步，判断标准是：{step.criteria}"
                "我这边还没配模型密钥，只能给你标准，你先对着它看一遍。"
            ),
            "basis": "none",
            "note": "没接模型，这条用的是步骤自带的合格标准，不是模型回答。",
            "model_name": None,
        }

    try:
        answer = chat(
            [
                {"role": "system", "content": ASK_SYSTEM},
                {"role": "user", "content": f"{_step_context(step)}\n\n用户的问题：{question}"},
            ],
            max_tokens=500,
            temperature=0.4,
        )
    except ModelError as exc:
        return {
            "answer": f"这次没能回答：{exc}你先照着合格标准对一遍，或者再问我一次。",
            "basis": "none",
            "note": "模型没调通。",
            "model_name": None,
        }

    return {
        "answer": answer,
        "basis": "model",
        "note": "模型写的，记得自己核对。",
        "model_name": settings.model_name,
    }
