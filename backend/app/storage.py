import shutil
from pathlib import Path

from app.config import settings


def save_file(source: Path, video_id: str) -> tuple[str, Path]:
    """Move a completed download into local durable storage."""
    extension = source.suffix.lower() or ".mp4"
    relative = Path("videos") / video_id / f"source{extension}"
    destination = settings.local_storage_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return relative.as_posix(), destination


def resolve_object(object_key: str) -> Path:
    """Resolve a database object key without allowing path traversal."""
    root = settings.local_storage_root.resolve()
    path = (root / object_key).resolve()
    if path != root and root not in path.parents:
        raise ValueError("无效的本地文件路径")
    return path


def delete_file(object_key: str) -> None:
    """Delete one stored video and its now-empty per-video directory."""
    path = resolve_object(object_key)
    if path.exists():
        if not path.is_file():
            raise ValueError("视频存储路径不是文件")
        path.unlink()

    videos_root = (settings.local_storage_root / "videos").resolve()
    parent = path.parent
    if parent != videos_root and videos_root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            # Keep the directory if it still contains another legitimate file.
            pass
