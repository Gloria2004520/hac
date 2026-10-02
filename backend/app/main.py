from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, create_tables, get_db
from app.local_queue import executor, submit
from app.models import Video
from app.schemas import PlaybackRead, SearchResponse, VideoCreate, VideoRead
from app.search import SearchBusy, SearchTimeout, SearchUpstreamError, search_youtube
from app.security import UnsafeURLError, validate_source_url
from app.storage import delete_file, resolve_object
from app.tasks import download_video


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    session = SessionLocal()
    interrupted_ids: list[str] = []
    try:
        interrupted = session.scalars(
            select(Video).where(
                Video.status.in_(
                    ["pending", "inspecting", "downloading", "processing", "uploading"]
                )
            )
        ).all()
        for video in interrupted:
            video.status = "pending"
            video.progress = 0
            interrupted_ids.append(video.id)
        session.commit()
    finally:
        session.close()
    for video_id in interrupted_ids:
        submit(download_video, video_id)
    try:
        yield
    finally:
        executor.shutdown(wait=False, cancel_futures=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)


def _submit_download(video: Video, db: Session) -> None:
    try:
        submit(download_video, video.id)
    except Exception as exc:
        video.status = "failed"
        video.error_message = "本地下载队列暂不可用"
        db.commit()
        raise HTTPException(status_code=503, detail="本地下载队列暂不可用") from exc


def _reuse_video(video: Video, payload: VideoCreate, db: Session) -> Video:
    if video.status != "failed":
        return video
    video.source_url = str(payload.url)
    video.source_platform = payload.source_platform or video.source_platform
    video.source_video_id = payload.source_video_id or video.source_video_id
    video.title = payload.title or video.title
    video.uploader = payload.uploader or video.uploader
    video.thumbnail_url = str(payload.thumbnail_url) if payload.thumbnail_url else video.thumbnail_url
    video.duration_seconds = (
        payload.duration_seconds if payload.duration_seconds is not None else video.duration_seconds
    )
    video.status = "pending"
    video.progress = 0
    video.error_message = None
    db.commit()
    db.refresh(video)
    _submit_download(video, db)
    return video


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.post("/api/videos", response_model=VideoRead, status_code=status.HTTP_202_ACCEPTED)
def create_video(payload: VideoCreate, db: Session = Depends(get_db)):
    source_url = str(payload.url)
    try:
        validate_source_url(source_url, settings.allowed_domains)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing = None
    if payload.source_platform and payload.source_video_id:
        existing = db.scalar(
            select(Video).where(
                func.lower(Video.source_platform) == payload.source_platform,
                Video.source_video_id == payload.source_video_id,
            )
        )
    if existing is None:
        existing = db.scalar(select(Video).where(Video.source_url == source_url))
    if existing is not None:
        return _reuse_video(existing, payload, db)

    video = Video(
        source_url=source_url,
        source_platform=payload.source_platform,
        source_video_id=payload.source_video_id,
        title=payload.title,
        uploader=payload.uploader,
        thumbnail_url=str(payload.thumbnail_url) if payload.thumbnail_url else None,
        duration_seconds=payload.duration_seconds,
        status="pending",
        progress=0,
    )
    db.add(video)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if payload.source_platform and payload.source_video_id:
            existing = db.scalar(
                select(Video).where(
                    func.lower(Video.source_platform) == payload.source_platform,
                    Video.source_video_id == payload.source_video_id,
                )
            )
        if existing is not None:
            return _reuse_video(existing, payload, db)
        raise
    db.refresh(video)

    _submit_download(video, db)
    return video


@app.get("/api/search", response_model=SearchResponse)
def search_videos(
    q: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db),
):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入要搜索的菜名")
    try:
        items, cached = search_youtube(db, query)
    except SearchTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail="检索超时，可稍后重试或直接粘贴视频链接",
        ) from exc
    except SearchBusy as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except SearchUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    candidate_ids = [item["platform_video_id"] for item in items]
    saved_ids: set[str] = set()
    if candidate_ids:
        saved_ids = set(
            db.scalars(
                select(Video.source_video_id).where(
                    func.lower(Video.source_platform) == "youtube",
                    Video.source_video_id.in_(candidate_ids),
                    Video.status != "failed",
                )
            ).all()
        )
    for item in items:
        item["already_saved"] = item["platform_video_id"] in saved_ids
    return SearchResponse(query=query, cached=cached, count=len(items), items=items)


@app.get("/api/videos", response_model=list[VideoRead])
def list_videos(db: Session = Depends(get_db)):
    return db.scalars(select(Video).order_by(Video.created_at.desc()).limit(50)).all()


@app.get("/api/videos/{video_id}", response_model=VideoRead)
def get_video(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return video


@app.get("/api/videos/{video_id}/playback", response_model=PlaybackRead)
def get_playback(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if video.status != "ready" or not video.object_key:
        raise HTTPException(status_code=409, detail="视频尚未准备完成")
    return PlaybackRead(url=f"/api/videos/{video.id}/content")


@app.get("/api/videos/{video_id}/content")
def get_video_content(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if video.status != "ready" or not video.object_key:
        raise HTTPException(status_code=409, detail="视频尚未准备完成")
    try:
        path = resolve_object(video.object_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="视频文件不存在")
    return FileResponse(
        path,
        media_type=video.mime_type,
        filename=path.name,
        content_disposition_type="inline",
    )


@app.delete("/api/videos/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: str, db: Session = Depends(get_db)):
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if video.status not in {"ready", "failed"}:
        raise HTTPException(status_code=409, detail="视频仍在处理中，请完成后再删除")

    if video.object_key:
        try:
            delete_file(video.object_key)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail="本地视频文件删除失败") from exc

    db.delete(video)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
