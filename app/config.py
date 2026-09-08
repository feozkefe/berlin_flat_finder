import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str = ""
    host: str = "127.0.0.1"
    port: int = 8080
    data_dir: str = ""
    scan_on_start: bool = False
    request_timeout: float = 20.0
    max_pages_per_source: int = 2
    max_listings_per_source: int = 40
    max_telegram_per_scan: int = 15


settings = Settings()

# Railway / Docker: bind all interfaces when a platform PORT is injected.
if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    settings.host = "0.0.0.0"

DATA_DIR = Path(settings.data_dir) if settings.data_dir else ROOT_DIR / "data"
DB_PATH = DATA_DIR / "finder.db"
