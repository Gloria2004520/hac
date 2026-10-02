from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# 仓库根目录，前后端共用同一个 .env
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "CookClip"
    database_url: str = "sqlite:///./data/cookclip.db"
    local_storage_root: Path = Path("./data/storage")
    local_workers: int = 2
    search_timeout_seconds: int = 8
    search_fetch_limit: int = 20
    search_result_limit: int = 12
    search_cache_ttl_seconds: int = 6 * 60 * 60
    search_empty_cache_ttl_seconds: int = 60 * 60
    search_max_concurrent: int = 1

    max_video_duration_seconds: int = 3600
    max_file_size_bytes: int = 2 * 1024 * 1024 * 1024
    temp_root: Path = Path("/tmp/cookclip")
    yt_dlp_cookie_file: str | None = None
    allowed_video_domains: str = (
        "youtube.com,youtu.be,bilibili.com,b23.tv,tiktok.com,instagram.com"
    )

    @property
    def allowed_domains(self) -> tuple[str, ...]:
        return tuple(
            item.strip().lower()
            for item in self.allowed_video_domains.split(",")
            if item.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
