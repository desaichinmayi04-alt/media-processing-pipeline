"""
Centralized configuration. Everything environment-driven so the same
codebase runs locally (SQLite + local disk) or in a real deployment
(Postgres + S3-compatible storage) without code changes.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # --- Database ---
    # Defaults to local SQLite so `docker compose up` / local runs need
    # zero external services. Set DATABASE_URL to a Postgres DSN in
    # production (e.g. postgresql+psycopg2://user:pass@host/db).
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./storage/app.db")

    # --- Queue / broker ---
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Storage ---
    # Local disk by default. Swapping to S3 only requires changing
    # app/storage.py's implementation — the rest of the app depends on
    # the StorageBackend interface, not the disk directly.
    storage_dir: Path = Path(os.getenv("STORAGE_DIR", "./storage/uploads"))

    # --- Upload limits ---
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "15"))
    allowed_content_types: tuple = ("image/jpeg", "image/png", "image/webp")

    # --- Analysis thresholds (tunable without code changes) ---
    blur_laplacian_threshold: float = float(os.getenv("BLUR_THRESHOLD", "100.0"))
    dark_brightness_threshold: float = float(os.getenv("DARK_THRESHOLD", "50.0"))
    bright_overexposed_threshold: float = float(os.getenv("BRIGHT_THRESHOLD", "220.0"))
    duplicate_hash_distance: int = int(os.getenv("DUPLICATE_HASH_DISTANCE", "5"))


settings = Settings()
settings.storage_dir.mkdir(parents=True, exist_ok=True)
