import json
import math
import os
import re
import signal
import subprocess
import sys
import threading
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import SearchCache


class SearchError(RuntimeError):
    pass


class SearchTimeout(SearchError):
    pass


class SearchBusy(SearchError):
    pass


class SearchUpstreamError(SearchError):
    pass


_query_locks: dict[str, threading.Lock] = {}
_query_locks_guard = threading.Lock()
_search_slots = threading.BoundedSemaphore(settings.search_max_concurrent)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip().lower())


def _compact(value: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", value.lower())


def _query_lock(cache_key: str) -> threading.Lock:
    with _query_locks_guard:
        return _query_locks.setdefault(cache_key, threading.Lock())


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# 这些字样说明「根本连不上」，而不是「平台限流」——两者要给用户完全不同的提示
UNREACHABLE_MARKERS = (
    "timed out",
    "unable to download webpage",
    "failed to resolve",
    "name or service not known",
    "connection refused",
    "connection reset",
    "proxyerror",
    "network is unreachable",
    "no route to host",
)


def _tail(partial: str) -> str:
    return " / ".join(line.strip() for line in partial.splitlines() if line.strip())[-300:]


def _failure_reason(partial: str) -> str:
    """检索失败时给用户一句真话：是网络到不了，还是平台限流，还是别的原因。"""
    tail = _tail(partial)
    lower = tail.lower()
    if "429" in tail or "too many requests" in lower:
        return "视频平台当前限制了搜索请求，请稍后重试。"
    if any(marker in lower for marker in UNREACHABLE_MARKERS):
        return (
            "本机连不上 YouTube"
            + (f"（{tail}）" if tail else "")
            + "。检索需要能访问 YouTube 的网络；可以先粘贴视频链接，或者换一个能访问的平台。"
        )
    return "检索失败了" + (f"（{tail}）" if tail else "，原因未知") + "，可以稍后重试或直接粘贴视频链接。"


def _timeout_reason(partial: str, seconds: int) -> str:
    """超时到底是「网络到不了」还是「平台慢」，如实说清楚，别让用户瞎猜。"""
    tail = _tail(partial)
    if any(marker in tail.lower() for marker in UNREACHABLE_MARKERS):
        return (
            f"等了 {seconds} 秒，本机连不上 YouTube"
            + (f"（{tail}）" if tail else "")
            + "。检索需要能访问 YouTube 的网络；可以先粘贴视频链接，或者换一个能访问的平台。"
        )
    return (
        f"等了 {seconds} 秒还没拿到结果"
        + (f"（{tail}）" if tail else "")
        + "，可以稍后重试，或直接粘贴视频链接。"
    )


def _payload_or_failure(stdout: str, stderr: str, returncode: int) -> dict[str, Any]:
    """把子进程的输出判定成「结果」还是「失败」。

    ⚠️ 这里踩过一个坑：yt-dlp 带了 --ignore-errors，整页检索失败时**照样会吐出 JSON**
    （entries 里全是 null，返回码却是 1）。只判断「stdout 是否为空」会把它当成
    「没搜到」，然后缓存一小时——对用户就是撒谎。所以返回码非 0 且没有一条可用
    结果时，一律按失败报出去。
    """
    if not stdout.strip():
        raise SearchUpstreamError(_failure_reason(stderr))

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise SearchUpstreamError("视频平台返回了无法识别的搜索结果") from exc

    usable = [entry for entry in (payload.get("entries") or []) if entry and entry.get("id")]
    if not usable and returncode != 0:
        raise SearchUpstreamError(_failure_reason(stderr))
    return payload


def _run_search_process(query: str) -> dict[str, Any]:
    search_term = f"ytsearch{settings.search_fetch_limit}:{query} 教程"
    command = [
        sys.executable,
        "-m",
        "yt_dlp",
        search_term,
        "--flat-playlist",
        "--dump-single-json",
        "--skip-download",
        "--playlist-end",
        str(settings.search_fetch_limit),
        "--socket-timeout",
        str(settings.search_socket_timeout_seconds),
        "--retries",
        "1",
        "--extractor-retries",
        "1",
        "--no-warnings",
        "--ignore-errors",
    ]
    if settings.yt_dlp_cookie_file:
        command.extend(["--cookies", settings.yt_dlp_cookie_file])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=settings.search_timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        # 超时前 yt-dlp 已经打出来的报错别丢掉——它才说明到底是网络还是平台的问题
        partial = _as_text(getattr(exc, "stderr", None)) or _as_text(getattr(exc, "output", None))
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (AttributeError, ProcessLookupError):
            process.kill()
        process.communicate()
        raise SearchTimeout(_timeout_reason(partial, settings.search_timeout_seconds)) from exc

    return _payload_or_failure(stdout, stderr, process.returncode)


def _thumbnail(entry: dict[str, Any]) -> str | None:
    if entry.get("thumbnail"):
        return str(entry["thumbnail"])
    thumbnails = entry.get("thumbnails") or []
    for candidate in reversed(thumbnails):
        if candidate.get("url"):
            return str(candidate["url"])
    return None


def _score(query: str, item: dict[str, Any], max_views: int) -> float:
    title = str(item.get("title") or "")
    compact_query = _compact(query)
    compact_title = _compact(title)

    aliases = {
        "番茄": "西红柿",
        "西红柿": "番茄",
        "鸡蛋": "蛋",
        "土豆": "马铃薯",
        "马铃薯": "土豆",
    }
    query_variants = {compact_query}
    for source, replacement in aliases.items():
        for value in list(query_variants):
            if source in value:
                query_variants.add(value.replace(source, replacement))
    title_match = 1.0 if any(value and value in compact_title for value in query_variants) else 0.25

    duration = item.get("duration")
    if duration is None:
        duration_score = 0.35
    elif 60 <= duration <= 900:
        duration_score = 1.0
    elif 30 <= duration <= 1800:
        duration_score = 0.5
    else:
        duration_score = 0.0

    views = max(0, int(item.get("view_count") or 0))
    view_score = math.log(views + 1) / math.log(max_views + 1) if max_views else 0.0
    positive = ("做法", "教程", "家常", "教你", "步骤", "零失败")
    negative = ("测评", "探店", "试吃", "vlog", "合集")
    keyword_score = 0.5 + 0.1 * sum(word in title.lower() for word in positive)
    keyword_score -= 0.15 * sum(word in title.lower() for word in negative)
    keyword_score = min(1.0, max(0.0, keyword_score))

    return round(
        0.45 * title_match
        + 0.25 * duration_score
        + 0.20 * view_score
        + 0.10 * keyword_score,
        4,
    )


def parse_search_payload(query: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = [entry for entry in (payload.get("entries") or []) if entry and entry.get("id")]
    max_views = max((int(entry.get("view_count") or 0) for entry in raw_entries), default=0)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw_entries:
        video_id = str(entry["id"])
        if video_id in seen:
            continue
        seen.add(video_id)
        title = str(entry.get("title") or "未命名视频")
        duration = entry.get("duration")
        views = entry.get("view_count")
        item = {
            "candidate_id": f"youtube:{video_id}",
            "platform": "youtube",
            "platform_video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": title,
            "uploader": entry.get("uploader") or entry.get("channel"),
            "duration_seconds": float(duration) if duration is not None else None,
            "view_count": int(views) if views is not None else None,
            "thumbnail_url": _thumbnail(entry),
        }
        item["score"] = _score(query, entry, max_views)
        items.append(item)
    items.sort(key=lambda item: item["score"], reverse=True)
    return items[: settings.search_result_limit]


def _cached(db: Session, cache_key: str) -> list[dict[str, Any]] | None:
    cached = db.get(SearchCache, cache_key)
    now = int(time.time())
    if cached is None or cached.expires_at_epoch <= now:
        if cached is not None:
            db.delete(cached)
            db.commit()
        return None
    try:
        return json.loads(cached.results_json)
    except json.JSONDecodeError:
        db.delete(cached)
        db.commit()
        return None


def search_youtube(db: Session, query: str) -> tuple[list[dict[str, Any]], bool]:
    normalized = normalize_query(query)
    cache_key = f"youtube:v2:{normalized}"
    cached = _cached(db, cache_key)
    if cached is not None:
        return cached, True

    with _query_lock(cache_key):
        cached = _cached(db, cache_key)
        if cached is not None:
            return cached, True
        if not _search_slots.acquire(timeout=2):
            raise SearchBusy("当前已有检索正在进行，请稍后重试")
        try:
            payload = _run_search_process(normalized)
            items = parse_search_payload(normalized, payload)
        finally:
            _search_slots.release()

        now = int(time.time())
        ttl = settings.search_cache_ttl_seconds if items else settings.search_empty_cache_ttl_seconds
        record = SearchCache(
            cache_key=cache_key,
            query=normalized,
            backend="youtube",
            results_json=json.dumps(items, ensure_ascii=False),
            created_at_epoch=now,
            expires_at_epoch=now + ttl,
        )
        db.merge(record)
        db.commit()
        return items, False
