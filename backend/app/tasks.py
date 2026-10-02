import mimetypes
import re
import tempfile
import time
from pathlib import Path

import yt_dlp
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Video
from app.storage import save_file


MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


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

        with yt_dlp.YoutubeDL({**common_options, "skip_download": True}) as downloader:
            info = downloader.extract_info(video.source_url, download=False)

        if info.get("is_live"):
            raise ValueError("暂不支持直播链接")
        duration = info.get("duration")
        if duration and duration > settings.max_video_duration_seconds:
            raise ValueError(f"视频超过允许的最长时长：{settings.max_video_duration_seconds} 秒")

        _update(
            session,
            video,
            status="downloading",
            title=info.get("title"),
            uploader=info.get("uploader"),
            thumbnail_url=info.get("thumbnail"),
            duration_seconds=duration,
            source_video_id=info.get("id"),
            source_platform=(info.get("extractor_key") or info.get("extractor") or "").lower() or None,
        )

        with tempfile.TemporaryDirectory(prefix=f"{video_id}-", dir=settings.temp_root) as temp_dir:
            job_dir = Path(temp_dir)

            def progress_hook(data: dict) -> None:
                nonlocal last_progress_write
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
                "format": (
                    "bv*[vcodec^=avc1][protocol=https][height<=1080]"
                    "+ba[acodec^=mp4a][protocol=https]"
                    "/b[ext=mp4][protocol=https]"
                    "/bv*[ext=mp4][protocol=https][height<=1080]"
                    "+ba[ext=m4a][protocol=https]"
                    "/bv*+ba/b"
                ),
                "merge_output_format": "mp4",
                "max_filesize": settings.max_file_size_bytes,
                "concurrent_fragment_downloads": 1,
                "progress_hooks": [progress_hook],
                "postprocessor_hooks": [postprocessor_hook],
                "writethumbnail": False,
                "writesubtitles": False,
                "writeautomaticsub": False,
            }
            with yt_dlp.YoutubeDL(download_options) as downloader:
                downloader.extract_info(video.source_url, download=True)

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
    except Exception as exc:
        session.rollback()
        video = session.get(Video, video_id)
        if video is not None:
            message = ANSI_ESCAPE.sub("", str(exc))
            _update(session, video, status="failed", error_message=message[:2000])
        raise
    finally:
        session.close()
