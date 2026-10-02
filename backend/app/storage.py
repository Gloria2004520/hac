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


# ---------- 步骤代表帧 ----------


def frame_key(video_id: str, breakdown_id: str, position: int) -> str:
    """代表帧的存储路径。按 breakdown 分目录，重拆时旧的整目录删掉就行。"""
    return (Path("frames") / video_id / breakdown_id / f"step-{position:02d}.jpg").as_posix()


def save_frame(data: bytes, relative: str) -> Path:
    path = resolve_object(relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def delete_frames_for(video_id: str, breakdown_id: str | None = None) -> None:
    """删掉某条视频（或某一次分解）的代表帧目录。路径一律经 resolve_object 校验。"""
    target = Path("frames") / video_id
    if breakdown_id:
        target = target / breakdown_id
    path = resolve_object(target.as_posix())
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        # 顺手把空的 video 层收掉，别留一堆空目录
        parent = path.parent
        if parent.name == video_id:
            try:
                parent.rmdir()
            except OSError:
                pass
