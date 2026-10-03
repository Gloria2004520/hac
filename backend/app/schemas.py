from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class VideoCreate(BaseModel):
    url: HttpUrl
    source_platform: Literal["youtube"] | None = None
    source_video_id: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=500)
    uploader: str | None = Field(default=None, max_length=300)
    thumbnail_url: HttpUrl | None = None
    duration_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def source_identity_is_complete(self):
        if bool(self.source_platform) != bool(self.source_video_id):
            raise ValueError("来源平台和平台视频 ID 必须同时提供")
        return self


class VideoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_url: str
    source_platform: str | None
    source_video_id: str | None
    title: str | None
    uploader: str | None
    thumbnail_url: str | None
    duration_seconds: float | None
    status: str
    progress: int
    error_message: str | None
    bucket_name: str | None
    object_key: str | None
    file_size: int | None
    mime_type: str | None
    saved: bool
    created_at: datetime
    updated_at: datetime


class PlaybackRead(BaseModel):
    url: str


class SearchItem(BaseModel):
    candidate_id: str
    platform: Literal["youtube"]
    platform_video_id: str
    url: str
    title: str
    uploader: str | None = None
    duration_seconds: float | None = None
    view_count: int | None = None
    thumbnail_url: str | None = None
    score: float
    already_saved: bool = False


class SearchResponse(BaseModel):
    query: str
    cached: bool
    count: int
    items: list[SearchItem]


class SavedTutorial(BaseModel):
    """「存下来，慢慢做」列表里的一条。带上进度，用户一眼知道做到哪了。"""

    id: str
    title: str | None
    uploader: str | None
    duration_seconds: float | None
    thumbnail_url: str | None
    status: str
    saved_at: datetime | None
    # 已经拆出来了多少步、其中勾了几步。还没拆就是 0 / 0。
    step_total: int = 0
    step_done: int = 0


class LibraryItem(BaseModel):
    """素材库中的一条：只代表最新一次成功分解，不把通用骨架算作素材。"""

    id: str
    title: str
    display_title: str
    uploader: str | None
    duration_seconds: float | None
    category: Literal["cooking", "tools", "other"]
    category_label: str
    icon: Literal["cooking", "tools", "other"]
    category_basis: Literal["model", "rule"]
    step_total: int
    step_done: int
    breakdown_basis: Literal["shots", "even"]
    updated_at: datetime


# ---------- 步骤（分解 + 检查） ----------


class StepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    title: str
    summary: str
    question: str
    criteria: str
    hint: str | None
    start_seconds: float | None
    end_seconds: float | None
    # 段边界怎么来的：shots=真实画面切换，even=总时长平均分，mock=通用骨架
    basis: Literal["mock", "sample", "shots", "even", "manual"]
    # 标题/说明/合格标准怎么来的：model=视觉模型看了代表帧写的，none=没人写（只有画面）
    text_basis: Literal["model", "none"]
    # 有没有留下这一段的代表画面（前端按 step id 取 /frame）
    has_frame: bool
    done: bool
    done_at: datetime | None
    user_note: str | None
    last_verdict: Literal["pass", "retry", "unclear"] | None
    last_reason: str | None
    last_checked_at: datetime | None


class StepsResponse(BaseModel):
    video_id: str
    title: str | None
    total: int
    done_count: int
    # 整份步骤都是通用骨架、一个字都没读视频时才是 true
    mock: bool
    # 是否配了能看图的模型。没配的话，用户传的照片只会留给他自己对照，不会发给模型。
    vision_ready: bool
    # 后台正在拆，前端轮询等它变 false
    analyzing: bool = False
    # 视频还没下载完，现在没有步骤可给
    waiting: bool = False
    # 这份步骤用的方法：shots / even / mock / None（还没拆过）
    basis: str | None = None
    # 留下了几张代表画面
    frame_count: int = 0
    note: str
    steps: list[StepRead]


class StepUpdate(BaseModel):
    done: bool | None = None
    user_note: str | None = Field(default=None, max_length=500)


class StepCheckRequest(BaseModel):
    report: str = Field(min_length=1, max_length=2000)
    # 可选的照片，data:image/...;base64,...
    image_data_url: str | None = Field(default=None, max_length=8_000_000)


class StepCheckResponse(BaseModel):
    verdict: Literal["pass", "retry", "unclear"]
    reason: str
    detail: str
    basis: Literal["model", "fallback", "none"]
    note: str
    model_name: str | None
    step: StepRead


class StepAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=600)


class StepAskResponse(BaseModel):
    answer: str
    basis: Literal["model", "fallback", "none"]
    note: str
    model_name: str | None
