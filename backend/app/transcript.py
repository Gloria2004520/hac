"""Fetch subtitle text on demand. This does not perform visual video analysis."""
import html
import json
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

_slot = threading.BoundedSemaphore(1)
_stamp = re.compile(r"(?:(\d{2,}):)?(\d{2}):(\d{2})[.,](\d{3})")


def seconds(value: str) -> float:
    match = _stamp.fullmatch(value.strip())
    if not match:
        raise ValueError("无效字幕时间")
    hours, minutes, secs, millis = match.groups()
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(secs) + int(millis) / 1000


def parse_vtt(text: str) -> list[dict]:
    segments = []
    lines = text.replace("\r", "").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        index += 1
        if "-->" not in line:
            continue
        try:
            start, end = line.split("-->", 1)
            start_time = seconds(start)
            end_time = seconds(end.strip().split()[0])
        except (ValueError, IndexError):
            continue
        content = []
        while index < len(lines) and lines[index].strip():
            content.append(lines[index])
            index += 1
        caption = html.unescape(re.sub(r"<[^>]*>", "", " ".join(content))).strip()
        if not caption or end_time <= start_time:
            continue
        # YouTube automatic captions repeat the preceding line in rolling cues.
        if segments and caption == segments[-1]["text"]:
            segments[-1]["end"] = end_time
            continue
        segments.append({"id": len(segments) + 1, "start": start_time, "end": end_time, "text": caption[:1000]})
    return segments


def get_transcript(video, settings, resolve_object) -> dict:
    if video.status != "ready" or not video.object_key:
        raise ValueError("请等待视频下载完成后提取字幕，也可以先粘贴教程文字")
    local_video = resolve_object(video.object_key)
    cache = local_video.parent / "transcript.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    if not _slot.acquire(blocking=False):
        raise RuntimeError("已有字幕任务正在处理，请稍后重试")
    try:
        with tempfile.TemporaryDirectory(prefix="cookclip-subtitles-") as directory:
            command = [sys.executable, "-m", "yt_dlp", "--skip-download", "--no-playlist", "--quiet",
                       "--no-warnings", "--write-subs", "--write-auto-subs", "--sub-langs", "zh-Hans,zh-Hant,zh,en",
                       "--sub-format", "vtt", "--socket-timeout", "8", "--retries", "0",
                       "--output", str(Path(directory) / "source.%(ext)s")]
            if settings.yt_dlp_cookie_file:
                command.extend(["--cookies", settings.yt_dlp_cookie_file])
            command.extend(["--", video.source_url])
            try:
                result = subprocess.run(command, capture_output=True, timeout=40, check=False)
            except subprocess.TimeoutExpired as exc:
                raise ValueError("字幕提取超时，请稍后重试或粘贴教程文字") from exc
            paths = sorted(Path(directory).glob("*.vtt"), key=lambda path: (".en." in path.name, path.name))
            if not paths:
                message = "视频没有可用字幕，请粘贴教程文字" if result.returncode == 0 else "视频平台未能提供字幕，请粘贴教程文字"
                raise ValueError(message)
            segments = parse_vtt(paths[0].read_text(encoding="utf-8"))
            # Bound model context; never quietly analyse only the beginning of a long tutorial.
            if len(segments) > 300 or sum(len(s["text"]) for s in segments) > 20000:
                raise ValueError("字幕较长，请粘贴你想分解的操作片段（最多 20000 字）")
            if not segments:
                raise ValueError("字幕没有可用操作文字，请粘贴教程文字")
            data = {"source": "subtitle", "segments": segments}
            temporary = cache.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            temporary.replace(cache)
            return data
    finally:
        _slot.release()
