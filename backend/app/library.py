"""素材库标题与分类。

AI 只拿到教程标题和步骤文字；步骤文字最多来自每段的一张代表截图，绝不把分类说成
理解了整段视频。新增调用只允许默认的免费模型，避免素材整理产生付费请求。
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.coach import ModelError, chat, parse_loose_json
from app.config import settings

CATEGORY_LABELS = {
    "cooking": "做饭教程",
    "tools": "日常工具",
    "other": "其他教程",
}

_COOKING_WORDS = (
    "做饭", "做菜", "烹饪", "菜谱", "食谱", "厨房", "炒", "煮", "蒸", "烤", "煎",
    "炖", "焖", "凉拌", "厨师", "鸡蛋", "番茄", "西红柿", "鸡", "鸭", "鱼", "虾", "肉",
    "豆腐", "面条", "米饭", "汤", "甜点", "蛋糕", "recipe", "cooking", "cook",
)
_TOOL_WORDS = (
    "工具", "螺丝", "扳手", "螺丝刀", "电钻", "钻孔", "锤子", "钳子", "万用表", "卷尺",
    "安装", "组装", "拆卸", "维修", "修理", "换灯", "换锁", "打印机", "咖啡机", "吸尘器",
    "tool", "repair", "install", "drill", "screwdriver", "wrench",
)


def keyword_category(title: str | None) -> tuple[str, str]:
    normalized = (title or "").casefold()
    if any(word in normalized for word in _COOKING_WORDS):
        return "cooking", "rule"
    if any(word in normalized for word in _TOOL_WORDS):
        return "tools", "rule"
    return "other", "rule"


def display_tutorial_title(title: str | None) -> str:
    cleaned = (title or "未命名").strip()
    quoted = re.search(r"[“「《]\s*([^”」》]{1,24}?)\s*[”」》]", cleaned)
    if quoted:
        cleaned = quoted.group(1).strip("：:，,。.!！?？ ")
    return cleaned if cleaned.endswith("教程") else f"{cleaned}教程"


def _free_model_ready() -> bool:
    return bool(settings.model_key) and settings.model_name.casefold().endswith(":free")


def classify_tutorials(entries: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """一次免费文本调用分类一批素材；失败时逐条退回透明的关键词规则。"""
    fallback = {
        str(entry["id"]): keyword_category(str(entry.get("title") or ""))
        for entry in entries
    }
    if not entries or not _free_model_ready():
        return fallback

    evidence = [
        {
            "id": str(entry["id"]),
            "title": str(entry.get("title") or "")[:300],
            "step_titles": [str(value)[:100] for value in entry.get("step_titles", [])[:10]],
        }
        for entry in entries[:20]
    ]
    prompt = (
        "把下面教程分到且只能分到一个类别：cooking=做饭/饮品/烘焙，"
        "tools=日常工具、设备使用或维修，other=其余生活教程。"
        "证据只有视频标题和由代表截图写出的步骤标题，没有音频或完整视频。"
        "只输出 JSON：{\"items\":[{\"id\":\"原 id\",\"category\":\"cooking|tools|other\"}]}\n"
        + json.dumps(evidence, ensure_ascii=False)
    )
    try:
        parsed = parse_loose_json(
            chat(
                [
                    {"role": "system", "content": "你是谨慎的教程素材分类器。只按给出的证据分类，不补充内容。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=700,
                temperature=0.0,
            )
        )
    except ModelError:
        return fallback

    for item in (parsed or {}).get("items", []):
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        category = str(item.get("category") or "")
        if item_id in fallback and category in CATEGORY_LABELS:
            fallback[item_id] = (category, "model")
    return fallback
