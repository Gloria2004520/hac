from contextlib import asynccontextmanager

import json
import logging
import threading
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import breakdown as breakdown_module
from app import video_analysis
from app.breakdown import build_steps, mock_note
from app.coach import ask_step, check_step
from app.config import settings
from app.database import SessionLocal, create_tables, get_db
from app.local_queue import executor, submit
from app.models import StepInteraction, TutorialBreakdown, TutorialStep, Video, utcnow
from app.schemas import (
    PlaybackRead,
    SavedTutorial,
    SearchResponse,
    StepAskRequest,
    StepAskResponse,
    StepCheckRequest,
    StepCheckResponse,
    StepRead,
    StepUpdate,
    StepsResponse,
    VideoCreate,
    VideoRead,
)
from app.search import SearchBusy, SearchTimeout, SearchUpstreamError, search_youtube
from app.security import UnsafeURLError, validate_source_url
from app.storage import (
    delete_file,
    delete_frames_for,
    frame_key as frame_storage_key,
    resolve_object,
    save_frame,
)
from app.tasks import download_video

logger = logging.getLogger("cookclip.breakdown")


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
            detail=f"检索超时：{exc}",
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
def list_videos(saved: bool | None = Query(default=None), db: Session = Depends(get_db)):
    """任务列表。带 saved=1 就只看存下来的教程。"""
    query = select(Video).order_by(Video.created_at.desc()).limit(50)
    if saved is not None:
        query = query.where(Video.saved_at.is_not(None) if saved else Video.saved_at.is_(None))
    return db.scalars(query).all()


@app.get("/api/saved-tutorials", response_model=list[SavedTutorial])
def list_saved_tutorials(db: Session = Depends(get_db)):
    """「存着慢慢做」列表：按存下时间倒序，带上做到第几步了。

    只看存下的，不掺别的——这个页面存在的意义就是「我打算回来做的那几个」。
    """
    videos = db.scalars(
        select(Video)
        .where(Video.saved_at.is_not(None))
        .order_by(Video.saved_at.desc())
        .limit(50)
    ).all()
    if not videos:
        return []

    counts: dict[str, tuple[int, int]] = {}
    rows = db.execute(
        select(
            TutorialStep.video_id,
            func.count(TutorialStep.id),
            func.sum(case((TutorialStep.done.is_(True), 1), else_=0)),
        )
        .where(TutorialStep.video_id.in_([video.id for video in videos]))
        .group_by(TutorialStep.video_id)
    ).all()
    for video_id, total, done in rows:
        counts[video_id] = (int(total or 0), int(done or 0))

    return [
        SavedTutorial(
            id=video.id,
            title=video.title,
            uploader=video.uploader,
            duration_seconds=video.duration_seconds,
            thumbnail_url=video.thumbnail_url,
            status=video.status,
            saved_at=video.saved_at,
            step_total=counts.get(video.id, (0, 0))[0],
            step_done=counts.get(video.id, (0, 0))[1],
        )
        for video in videos
    ]


@app.post("/api/videos/{video_id}/save", response_model=VideoRead)
def toggle_save_video(video_id: str, db: Session = Depends(get_db)):
    """「存下来，慢慢做」：再点一次就是取消。进度和步骤本来就都在库里，
    这个标记的意思是「我以后还想做它」，方便之后按「存下的教程」列出来。"""
    video = _load_video(video_id, db)
    video.saved_at = None if video.saved_at else utcnow()
    db.commit()
    db.refresh(video)
    return video


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

    # 步骤和它们的代表帧跟着视频一起走，别在盘上留孤儿文件
    for step in _ordered_steps(video_id, db):
        db.delete(step)
    for interaction in db.scalars(
        select(StepInteraction).where(StepInteraction.video_id == video_id)
    ).all():
        db.delete(interaction)
    for record in db.scalars(
        select(TutorialBreakdown).where(TutorialBreakdown.video_id == video_id)
    ).all():
        db.delete(record)
    delete_frames_for(video_id)

    db.delete(video)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------- 步骤：真分解（ffmpeg 切点 + 视觉模型看图） + 检查 ----------

MAX_IMAGE_CHARS = 8_000_000

# 同一条视频的分解串行跑，避免背后两个请求同时解码同一份文件
_analysis_locks: dict[str, threading.Lock] = {}
_analysis_locks_guard = threading.Lock()
# 正在排队/正在跑的分解。放在内存里，是为了让 GET /steps 能立刻回答「还在拆」
_running_analyses: set[str] = set()


def _analysis_lock(video_id: str) -> threading.Lock:
    with _analysis_locks_guard:
        lock = _analysis_locks.get(video_id)
        if lock is None:
            lock = threading.Lock()
            _analysis_locks[video_id] = lock
        return lock


def _is_analyzing(video_id: str) -> bool:
    with _analysis_locks_guard:
        return video_id in _running_analyses


def _load_video(video_id: str, db: Session) -> Video:
    video = db.get(Video, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return video


def _ordered_steps(video_id: str, db: Session) -> list[TutorialStep]:
    return list(
        db.scalars(
            select(TutorialStep)
            .where(TutorialStep.video_id == video_id)
            .order_by(TutorialStep.position)
        ).all()
    )


def _latest_breakdown(video_id: str, db: Session) -> TutorialBreakdown | None:
    return db.scalars(
        select(TutorialBreakdown)
        .where(TutorialBreakdown.video_id == video_id)
        .order_by(TutorialBreakdown.created_at.desc())
        .limit(1)
    ).first()


def _local_video_path(video: Video) -> Path | None:
    """本地那份视频文件在哪。没有就说明还没下载完，或者文件被删了。"""
    if not video.object_key:
        return None
    try:
        path = resolve_object(video.object_key)
    except ValueError:
        return None
    return path if path.is_file() else None


def _load_step(video_id: str, step_id: str, db: Session) -> TutorialStep:
    step = db.get(TutorialStep, step_id)
    if step is None or step.video_id != video_id:
        raise HTTPException(status_code=404, detail="这一步不存在")
    return step


# ---------- 真分解 ----------


def build_breakdown(video_id: str, *, force: bool = False) -> str:
    """给一条视频做一次分解，结果落库。幂等：已经拆过就直接返回。

    自己开 session，因为要能在后台线程里跑。返回 "ready" / "failed" / "missing"。
    """
    session = SessionLocal()
    try:
        with _analysis_lock(video_id):
            video = session.get(Video, video_id)
            if video is None:
                return "missing"

            cached = _latest_breakdown(video_id, session)
            source = _local_video_path(video)

            if cached is not None and cached.status == "ready" and not force:
                # 已经拆过就复用。唯一的例外：上次因为没素材只给了骨架，现在素材到了。
                if not (cached.method == "mock" and source is not None):
                    return "ready"

            result: breakdown_module.Breakdown | None = None
            failure: str | None = None
            if source is not None:
                try:
                    result = breakdown_module.analyze(source)
                except (video_analysis.AnalysisError, OSError) as exc:
                    failure = str(exc)
                except Exception as exc:  # 别让一个奇怪的视频把整个页面打死
                    logger.exception("分解 %s 失败", video_id)
                    failure = f"分析这段视频时出错了：{exc}"
            else:
                failure = "这条视频还没下载到本地，所以只能先给你一套通用骨架。"

            record = TutorialBreakdown(
                video_id=video_id,
                method=result.method if result else breakdown_module.MOCK_BASIS,
                status="ready" if result else "failed",
                error_message=failure,
                duration_seconds=result.duration if result else video.duration_seconds,
                width=result.width if result else None,
                height=result.height if result else None,
                cuts_json=json.dumps(result.cuts) if result else None,
                segment_count=len(result.segments) if result else 0,
                captioned_count=result.captioned if result else 0,
                frame_count=0,
                model_name=result.model_name if result else None,
                note="",
            )
            session.add(record)
            session.flush()  # 拿到 record.id，代表帧要按它分目录

            # 旧的步骤和它们的判定历史一起清掉：位置都换了，留着只会对不上
            for step in _ordered_steps(video_id, session):
                session.delete(step)
            for interaction in session.scalars(
                select(StepInteraction).where(StepInteraction.video_id == video_id)
            ).all():
                session.delete(interaction)
            session.flush()
            # 代表帧也整目录重来
            delete_frames_for(video_id)

            if result is not None:
                for draft, segment in zip(result.drafts(), result.segments):
                    key = frame_storage_key(video_id, record.id, draft["position"])
                    try:
                        save_frame(segment.frame, key)
                    except OSError as exc:
                        logger.warning("代表帧写盘失败 %s：%s", key, exc)
                        key = None
                    session.add(
                        TutorialStep(video_id=video_id, breakdown_id=record.id, frame_key=key, **draft)
                    )
                record.frame_count = sum(
                    1 for step in _ordered_steps(video_id, session) if step.frame_key
                )
                record.note = breakdown_module.real_note(result)
            else:
                for draft in build_steps(video):
                    session.add(
                        TutorialStep(video_id=video_id, breakdown_id=record.id, **draft)
                    )
                record.note = f"这次没能真拆：{failure}{mock_note(video)}"

            session.commit()
            return record.status
    finally:
        session.close()


def _run_breakdown_job(video_id: str, force: bool = False) -> None:
    try:
        build_breakdown(video_id, force=force)
    except Exception:  # 后台任务不能把异常抛到线程池外面
        logger.exception("后台分解 %s 崩了", video_id)
    finally:
        with _analysis_locks_guard:
            _running_analyses.discard(video_id)


def _start_analysis(video_id: str, *, force: bool = False) -> None:
    """起一个后台分解。已经在跑就不重复起（force 也只是等它跑完，不再排一个）。"""
    with _analysis_locks_guard:
        if video_id in _running_analyses:
            return
        _running_analyses.add(video_id)
    try:
        submit(_run_breakdown_job, video_id, force)
    except Exception:
        with _analysis_locks_guard:
            _running_analyses.discard(video_id)
        raise HTTPException(status_code=503, detail="本地任务队列暂不可用，稍后再试")


def _needs_analysis(video: Video, record: TutorialBreakdown | None) -> bool:
    """现在该不该动手拆这一条。"""
    if record is None:
        return True
    if record.status == "running":
        return True
    if record.status == "failed":
        # 拆失败过就别自动重试了，免得每次刷新都白烧一遍 ffmpeg；交给用户点「重新分解」
        return False
    # 上次因为没素材只给了骨架，现在文件到了 → 值得真拆一次
    return record.method == breakdown_module.MOCK_BASIS and _local_video_path(video) is not None


def _steps_response(
    video: Video,
    steps: list[TutorialStep],
    record: TutorialBreakdown | None,
    *,
    analyzing: bool,
    waiting: bool,
) -> StepsResponse:
    note = record.note if record else ""
    if analyzing:
        if steps:
            # 页面上还挂着上一次的结果。骨架的话直说它马上会被换掉；
            # 真拆过的话就什么都别挂（否则会把上一次那段长说明又翻出来）
            note = (
                "下面这几步还是通用骨架。我正在按真实画面重新拆，一会儿会自动换掉，不用刷新。"
                if all(step.basis == breakdown_module.MOCK_BASIS for step in steps)
                else ""
            )
        else:
            note = "正在看画面。我会用 ffmpeg 找出画面真正切换的地方，再让看图的模型挨段看截图，可能要半分钟。"
    elif waiting and not steps:
        note = "视频还在下载。下载完我会自动按画面把它拆成一步步，到时候刷新这一页就行。"

    return StepsResponse(
        video_id=video.id,
        title=video.title,
        total=len(steps),
        done_count=sum(1 for step in steps if step.done),
        # 只有整份步骤都是骨架时才算 mock。混着的时候一律按真的说，界面上每步自己会标。
        mock=bool(steps) and all(step.basis == breakdown_module.MOCK_BASIS for step in steps),
        vision_ready=settings.model_vision_enabled and bool(settings.model_key),
        analyzing=analyzing,
        waiting=waiting,
        basis=record.method if record else None,
        frame_count=sum(1 for step in steps if step.frame_key),
        note=note,
        steps=[StepRead.model_validate(step) for step in steps],
    )


def _validate_image(image_data_url: str | None) -> str | None:
    if image_data_url is None:
        return None
    value = image_data_url.strip()
    if not value:
        return None
    if not value.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="照片格式不对，只接受 data:image/... 开头的图片")
    if len(value) > MAX_IMAGE_CHARS:
        raise HTTPException(status_code=413, detail="照片太大了，换一张小一点的")
    return value


@app.get("/api/videos/{video_id}/steps", response_model=StepsResponse)
def get_video_steps(video_id: str, db: Session = Depends(get_db)):
    """拿到这条视频的步骤。

    第一次访问（或素材刚到位）会自动起一个后台分解，这时返回 analyzing=true，
    前端轮询等它变成 false 即可——不要在这里同步跑，不然页面会卡住半分钟。
    """
    video = _load_video(video_id, db)
    source = _local_video_path(video)
    ready = video.status == "ready" and source is not None
    record = _latest_breakdown(video_id, db)

    if not ready:
        # 还没下载完：不给假步骤，就说清楚在等什么
        return _steps_response(video, [], record, analyzing=False, waiting=True)

    if _needs_analysis(video, record):
        _start_analysis(video_id)

    db.expire_all()
    video = _load_video(video_id, db)
    steps = _ordered_steps(video_id, db)
    record = _latest_breakdown(video_id, db)
    return _steps_response(
        video,
        steps,
        record,
        analyzing=_is_analyzing(video_id) or _needs_analysis(video, record),
        waiting=False,
    )


@app.post("/api/videos/{video_id}/steps/regenerate", response_model=StepsResponse)
def regenerate_video_steps(
    video_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """重新拆一次。

    界面上的按钮是**一次点击**就生效的：它会带上 force=1，因为按钮旁边就写着
    「重新拆一遍会换掉全部步骤」。这里保留 force 这道闸，是给直接打接口的场景兜底——
    有进度又没带 force 的话，先告诉调用方会丢什么，别让它悄悄清掉。
    """
    video = _load_video(video_id, db)
    if _local_video_path(video) is None:
        raise HTTPException(status_code=409, detail="这条视频还没下载到本地，没法重拆。")

    steps = _ordered_steps(video_id, db)
    done_count = sum(1 for step in steps if step.done)
    if done_count and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"你已经做到了 {done_count} 步。重新分解会换掉全部步骤，"
                "这些勾和判定记录都会清掉。确认的话带上 force=1 再来一次。"
            ),
        )

    # 后台跑，别把请求挂在这里等半分钟；前端拿到 analyzing=true 会自己轮询
    _start_analysis(video_id, force=True)
    db.expire_all()
    video = _load_video(video_id, db)
    steps = _ordered_steps(video_id, db)
    record = _latest_breakdown(video_id, db)
    return _steps_response(video, steps, record, analyzing=True, waiting=False)


@app.get("/api/videos/{video_id}/steps/{step_id}/frame")
def get_step_frame(video_id: str, step_id: str, db: Session = Depends(get_db)):
    """这一步的代表画面。没有就如实 404，不要拿别的图糊弄。"""
    _load_video(video_id, db)
    step = _load_step(video_id, step_id, db)
    if not step.frame_key:
        raise HTTPException(status_code=404, detail="这一步没有留下代表画面")
    try:
        path = resolve_object(step.frame_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="代表画面的路径不对") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="代表画面的文件不在了")
    return FileResponse(
        path,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.patch("/api/videos/{video_id}/steps/{step_id}", response_model=StepRead)
def update_step(
    video_id: str,
    step_id: str,
    payload: StepUpdate,
    db: Session = Depends(get_db),
):
    """用户自己勾「我做到了」/ 撤销，或者留一句备注。"""
    _load_video(video_id, db)
    step = _load_step(video_id, step_id, db)

    if payload.done is not None and payload.done != step.done:
        step.done = payload.done
        step.done_at = utcnow() if payload.done else None
        if not payload.done:
            # 撤销时把上一次判定一起清掉，免得出现「没做到但判定是通过」
            step.last_verdict = None
            step.last_reason = None
            step.last_checked_at = None
    if payload.user_note is not None:
        step.user_note = payload.user_note.strip() or None

    db.commit()
    db.refresh(step)
    return step


@app.post("/api/videos/{video_id}/steps/{step_id}/check", response_model=StepCheckResponse)
def check_video_step(
    video_id: str,
    step_id: str,
    payload: StepCheckRequest,
    db: Session = Depends(get_db),
):
    """「让小慢帮我看看」：按这一步的合格标准判定过没过。判定通过就自动记成做到了。"""
    video = _load_video(video_id, db)
    step = _load_step(video_id, step_id, db)
    image = _validate_image(payload.image_data_url)

    outcome = check_step(step, payload.report.strip(), image)

    step.last_verdict = outcome.verdict
    step.last_reason = outcome.reason
    step.last_checked_at = utcnow()
    if outcome.verdict == "pass":
        step.done = True
        step.done_at = utcnow()

    db.add(
        StepInteraction(
            video_id=video.id,
            step_id=step.id,
            kind="check",
            user_input=payload.report.strip(),
            has_image=bool(image),
            verdict=outcome.verdict,
            answer=outcome.reason,
            detail=outcome.detail or None,
            basis=outcome.basis,
            model_name=outcome.model_name,
        )
    )
    db.commit()
    db.refresh(step)

    return StepCheckResponse(
        verdict=outcome.verdict,
        reason=outcome.reason,
        detail=outcome.detail,
        basis=outcome.basis,
        note=outcome.note,
        model_name=outcome.model_name,
        step=StepRead.model_validate(step),
    )


@app.post("/api/videos/{video_id}/steps/{step_id}/ask", response_model=StepAskResponse)
def ask_video_step(
    video_id: str,
    step_id: str,
    payload: StepAskRequest,
    db: Session = Depends(get_db),
):
    """卡住了问一句。"""
    video = _load_video(video_id, db)
    step = _load_step(video_id, step_id, db)

    outcome = ask_step(step, payload.question.strip())

    db.add(
        StepInteraction(
            video_id=video.id,
            step_id=step.id,
            kind="ask",
            user_input=payload.question.strip(),
            basis=outcome["basis"],
            answer=outcome["answer"],
            model_name=outcome["model_name"],
        )
    )
    db.commit()
    return StepAskResponse(**outcome)
