"""
Centralized application configuration (Milestone 1).

All environment-driven configuration lives here. Nothing else in the
codebase should read os.environ / os.getenv directly from this point on —
anything that needs a config value takes a Settings instance (via the
get_settings dependency) instead.

`database_url` and `jwt_secret` are declared with no default, which means
pydantic-settings raises a ValidationError immediately if either is missing
when Settings() is instantiated. Combined with instantiating it eagerly at
import time in main.py, this is what gives us "fail fast on startup"
instead of discovering a missing secret on the first real request in
production.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development")

    # --- Required: app must refuse to start without these ---
    database_url: str
    jwt_secret: str

    # --- Have sensible defaults, but overridable ---
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 45
    jwt_refresh_token_expire_days: int = 14

    # --- S3-compatible storage (Milestone 10) and PDF document generation
    #     (Milestone 14) — both optional at the Settings level since a
    #     deployment that never touches those features doesn't need them. ---
    s3_endpoint_url: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_bucket_name: str | None = None

    # --- AI layer (Milestone 18) — `ai_enabled` gates whether /ai/* routes
    #     are even registered (see app/main.py's create_app); defaults to
    #     false, proving the rest of the app works with AI fully disabled.
    #     anthropic_api_key is read only inside workers/ai_tasks.py, at the
    #     point an AI task actually runs — never required to start the app,
    #     even with ai_enabled=true (only required once a task is queued). ---
    ai_enabled: bool = False
    anthropic_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached Settings instance — parses the environment/.env file
    only once per process, and guarantees every part of the app sees the
    exact same config values.

    Tests that need a different configuration than the process-wide one
    should override this via FastAPI's `app.dependency_overrides`, not by
    mutating environment variables after this module has already been
    imported (that's too late — the cache is already populated).
    """
    return Settings()
