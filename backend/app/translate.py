"""把已落库的中文步骤文案批量翻成英文。

为什么存在：步骤标题/说明/问题/合格标准是分解时（视觉模型）写好的中文，
落库后不再是界面短句，没法走 i18n.py 的字典。英文模式下第一次访问时
在这里现翻一次、存进 en_* 列，之后都是纯读库。

诚实底线：模型不可用或答不上来就返回 None，调用方原样退回中文并如实
提示「还没翻好」，绝不硬编、绝不假装翻过了。
"""

from __future__ import annotations

import json
from typing import Any

from app import coach

# 与 TutorialStep 的 en_* 列一一对应（hint 可为 None）
FIELDS = ("title", "summary", "question", "criteria", "hint")

SYSTEM = (
    "You translate Chinese tutorial step text into natural, simple English. "
    "Input is a JSON object: {\"steps\":[{\"i\":0,\"title\":...,\"summary\":...,"
    "\"question\":...,\"criteria\":...,\"hint\":...}]}. "
    "Output ONLY a JSON object {\"steps\":[{\"i\":0,...same keys...}]} with the same "
    "i values. Translate every field into friendly, easy-to-read English; keep null "
    "fields null; never add explanations or extra keys."
)


def translate_steps(items: list[dict[str, Any]]) -> dict[int, dict[str, Any]] | None:
    """翻一批步骤。成功返回 {输入下标: {field: 英文}}；任何失败返回 None。"""
    if not items:
        return {}
    try:
        payload = {
            "steps": [
                {"i": index, **{field: item.get(field) for field in FIELDS}}
                for index, item in enumerate(items)
            ]
        }
        raw = coach.chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            max_tokens=3000,
            temperature=0.1,
        )
    except coach.ModelError:
        return None

    data = coach.parse_loose_json(raw)
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        return None

    result: dict[int, dict[str, Any]] = {}
    for entry in data["steps"]:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(items):
            continue
        translated: dict[str, Any] = {}
        for field in FIELDS:
            value = entry.get(field)
            if isinstance(value, str) and value.strip():
                translated[field] = value.strip()
            elif value is None:
                translated[field] = None
        # 至少要有标题，这一条才算翻过
        if translated.get("title"):
            result[index] = translated
    return result or None
