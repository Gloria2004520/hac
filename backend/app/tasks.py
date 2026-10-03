import logging
import mimetypes
import re
import shutil
import tempfile
import time
from urllib.parse import urlparse
from pathlib import Path

import yt_dlp
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Video
from app.storage import save_file


MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

logger = logging.getLogger("cookclip.tasks")


def _friendly_error(message: str) -> str:
    """把 yt-dlp 的原始报错翻成人话，并直接给出能落地的下一步。

    页面那段红字用户是要照着做的，一段英文堆栈帮不了他。
    """
    lowered = message.lower()
    if "sign in to confirm" in lowered and "bot" in lowered:
        return (
            "YouTube 认为当前网络像机器人，要求登录验证。两条路："
            "① 用你登录过 YouTube 的浏览器导出一份 cookie（Netscape 格式），在 .env 里填 "
            "YT_DLP_COOKIE_FILE=cookie 文件路径，重启后端；"
            "② 或者换一个网络出口（比如手机热点）再试一次。"
        )
    if "sign in to confirm your age" in lowered or ("age" in lowered and "restrict" in lowered):
        return "这个视频有年龄限制，需要用登录过 YouTube 的账号 cookie 才能下载（.env 里配 YT_DLP_COOKIE_FILE）。"
    if "video unavailable" in lowered:
        return "YouTube 说这个视频看不了（可能下架、地区限制或被删除）。换一条视频试试。"
    if "private video" in lowered:
        return "这是一个私有视频，YouTube 不允许下载，换一条公开视频。"
    if "members-only" in lowered:
        return "这是频道会员专享视频，需要对应会员的 cookie 才能下载。"
    if "ffmpeg is not installed" in lowered or "ffmpeg not found" in lowered:
        return "没找到 ffmpeg。装好后把 .env 里的 FFMPEG_LOCATION 指到它的 bin 目录，重启后端。"
    if "unsupported url" in lowered or "is not a valid url" in lowered:
        return "这个链接解析不了。目前支持 YouTube 视频链接，检查一下是不是贴错了。"
    if "http error 429" in lowered or "too many requests" in lowered:
        return "YouTube 在限流，稍等几分钟再试。"
    return message


def _schedule_breakdown(video_id: str) -> None:
    """下载完顺手排一次分解。

    这样用户点「一步步做」时通常已经拆好了。失败也没关系——那条路线是幂等的，
    页面访问时还会再补一次。延迟 import 是为了避开 main <-> tasks 的循环依赖。
    """
    try:
        from app.main import _start_analysis

        _start_analysis(video_id)
    except Exception as exc:  # noqa: BLE001 - 后台预取失败不该影响下载结果
        logger.warning("视频 %s 下载完了，但没排上分解：%s", video_id, exc)


def _update(session: Session, video: Video, **values) -> None:
    for key, value in values.items():
        setattr(video, key, value)
    session.commit()


def _find_downloaded_file(directory: Path) -> Path:
    candidates = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES and not path.name.endswith(".part")
    ]
    if not candidates:
        raise RuntimeError("下载完成，但没有找到可用的视频文件")
    return max(candidates, key=lambda path: path.stat().st_size)


def _ffmpeg_location() -> str | None:
    """yt-dlp 合并音视频要用 ffmpeg。显式配置优先，找不到就让 yt-dlp 自己去找。"""
    if settings.ffmpeg_location:
        return settings.ffmpeg_location
    return shutil.which("ffmpeg")


def _reject_reason(info: dict) -> str | None:
    """下载前要拦掉的情况（直播 / 超长）。

    放在 match_filter 里判，这样**只需要一次网络提取**。原来是先单独提一次元信息、
    再提一次下载，而每次提取都要完整跑一遍播放器解析（实测约 4.3 秒），等于白等一倍。
    """
    if info.get("is_live"):
        return "暂不支持直播链接"
    duration = info.get("duration")
    if duration and duration > settings.max_video_duration_seconds:
        return f"视频超过允许的最长时长：{settings.max_video_duration_seconds} 秒"
    return None


def _format_selector() -> str:
    """优先 H.264 + AAC（合并成 mp4 不用重编码），清晰度不超过 MAX_VIDEO_HEIGHT。

    步骤卡片只用到 640px 宽的截图，1080p 多出来的像素基本都被丢掉，而视频文件却要
    完整下回来——降一档清晰度是下载耗时和数据量上最直接的一笔优化。
    """
    height = settings.max_video_height
    return (
        f"bv*[vcodec^=avc1][protocol=https][height<={height}]"
        "+ba[acodec^=mp4a][protocol=https]"
        "/b[ext=mp4][protocol=https]"
        f"/bv*[ext=mp4][protocol=https][height<={height}]"
        "+ba[ext=m4a][protocol=https]"
        "/bv*+ba/b"
    )


def download_video(video_id: str) -> None:
    session = SessionLocal()
    video = session.get(Video, video_id)
    if video is None:
        session.close()
        return

    settings.temp_root.mkdir(parents=True, exist_ok=True)
    last_progress_write = 0.0

    try:
        _update(session, video, status="inspecting", progress=0, error_message=None)

        common_options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 30,
            "retries": 10,
            "fragment_retries": 15,
        }
        if settings.yt_dlp_cookie_file:
            common_options["cookiefile"] = settings.yt_dlp_cookie_file
        elif settings.yt_dlp_cookie_browser == "chrome":
            host = (urlparse(video.source_url).hostname or "").lower()
            if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
                common_options["cookiesfrombrowser"] = ("chrome",)
        ffmpeg_path = _ffmpeg_location()
        if ffmpeg_path:
            common_options["ffmpeg_location"] = ffmpeg_path

        rejected: dict[str, str | None] = {"reason": None}
        metadata_written = False

        def _write_metadata(info_dict: dict) -> None:
            """把标题 / 时长先落库，页面在下载过程中就能显示，不用等下载完。"""
            nonlocal metadata_written
            if metadata_written:
                return
            metadata_written = True
            _update(
                session,
                video,
                title=info_dict.get("title"),
                uploader=info_dict.get("uploader"),
                thumbnail_url=info_dict.get("thumbnail"),
                duration_seconds=info_dict.get("duration"),
                source_video_id=info_dict.get("id"),
                source_platform=(
                    info_dict.get("extractor_key") or info_dict.get("extractor") or ""
                ).lower()
                or None,
            )

        def match_filter(info_dict, *, incomplete=False):
            """yt-dlp 在**下载之前**调用它：返回一句话就表示这条不要，直接中断。

            这样「直播 / 超长」的检查就和下载共用同一次提取，不再多跑一遍播放器解析。
            """
            if incomplete:
                return None
            reason = _reject_reason(info_dict)
            if reason:
                rejected["reason"] = reason
            return reason

        with tempfile.TemporaryDirectory(prefix=f"{video_id}-", dir=settings.temp_root) as temp_dir:
            job_dir = Path(temp_dir)

            def progress_hook(data: dict) -> None:
                nonlocal last_progress_write
                info_dict = data.get("info_dict")
                if isinstance(info_dict, dict):
                    # 一有进度就把标题/时长写进去，页面不用等下载完才有标题
                    _write_metadata(info_dict)
                if data.get("status") == "finished":
                    _update(session, video, status="downloading", progress=98)
                    return
                if data.get("status") != "downloading":
                    return
                now = time.monotonic()
                if now - last_progress_write < 1:
                    return
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                downloaded = data.get("downloaded_bytes") or 0
                progress = min(98, int(downloaded * 100 / total)) if total else video.progress
                _update(session, video, status="downloading", progress=progress)
                last_progress_write = now

            def postprocessor_hook(data: dict) -> None:
                if data.get("status") == "started":
                    _update(session, video, status="processing", progress=99)

            download_options = {
                **common_options,
                "outtmpl": str(job_dir / "source.%(ext)s"),
                "format": _format_selector(),
                "merge_output_format": "mp4",
                "max_filesize": settings.max_file_size_bytes,
                "concurrent_fragment_downloads": settings.download_concurrency,
                "match_filter": match_filter,
                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],
                "writethumbnail": False,
                "writesubtitles": False,
                "writeautomaticsub": False,
            }
            try:
                with yt_dlp.YoutubeDL(download_options) as downloader:
                    info = downloader.extract_info(video.source_url, download=True)
            except Exception as exc:
                # match_filter 拦下来的（直播 / 超长）要报我们自己的话，不是 yt-dlp 的英文
                if rejected["reason"]:
                    raise ValueError(rejected["reason"]) from exc
                raise
            # match_filter 拦下来时 yt-dlp **不抛异常**，只是静默跳过、什么都不下。
            # 不在这里兜住的话，下面会走到「找不到视频文件」，把用户引偏。
            if rejected["reason"]:
                raise ValueError(rejected["reason"])
            if isinstance(info, dict):
                _write_metadata(info)

            local_file = _find_downloaded_file(job_dir)
            file_size = local_file.stat().st_size
            if file_size > settings.max_file_size_bytes:
                raise ValueError("下载后文件超过允许的大小")

            content_type = mimetypes.guess_type(local_file.name)[0] or "application/octet-stream"
            _update(session, video, status="uploading", progress=99)
            object_key, stored_file = save_file(local_file, video_id)

            _update(
                session,
                video,
                status="ready",
                progress=100,
                storage_provider="local",
                bucket_name=None,
                object_key=object_key,
                file_size=stored_file.stat().st_size,
                mime_type=content_type,
            )
            # TemporaryDirectory removes the source and any yt-dlp fragments here.
        _schedule_breakdown(video_id)
    except Exception as exc:
        session.rollback()
        video = session.get(Video, video_id)
        if video is not None:
            message = _friendly_error(ANSI_ESCAPE.sub("", str(exc)))
            _update(session, video, status="failed", error_message=message[:2000])
        raise
    finally:
        session.close()
