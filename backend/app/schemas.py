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
