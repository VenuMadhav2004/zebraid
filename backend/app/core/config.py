from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_V1_PREFIX = "/api/v1"


class Settings(BaseSettings):
    """Backend settings loaded from environment variables / backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ZebraID API"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Root log level for the app (DEBUG, INFO, WARNING, ERROR)
    log_level: str = "INFO"

    # Supabase PostgreSQL connection string, e.g.
    # postgresql+psycopg://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
    database_url: str = ""

    # Connection pool. Keep small: Supabase session pooler limits client connections.
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800

    # Supabase project (server-side only; never expose service role key to the frontend)
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "zebra_images"
    storage_max_upload_bytes: int = 10 * 1024 * 1024  # keep equal to the bucket file_size_limit
    storage_signed_url_default_ttl: int = 60  # seconds
    storage_signed_url_max_ttl: int = 3600  # seconds

    # Gemini assistant (server-side only; empty => assistant reports unavailable)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 45.0
    gemini_max_context_chars: int = 32_000

    # Scientific analysis worker limits (configurable for 8 GB laptops)
    analysis_max_pixels: int = 4_000_000
    analysis_max_source_pixels: int = 12_000_000
    analysis_max_dimension: int = 8192
    analysis_queue_limit: int = 3
    analysis_timeout_seconds: int = 120
    analysis_tmp_dir: str = ""
    science_vendor_dir: str = ""

    # MegaDescriptor-L-384 v1 CPU recognition settings (server-side only; never commit checkpoints)
    recognition_model_path: str = ""
    recognition_gallery_cache_path: str = ""
    recognition_preprocessing: str = "model_card"
    recognition_top_k_default: int = 5
    recognition_timeout_seconds: int = 120
    # Load the checkpoint in a background thread when the API starts (≈75 s, ≈2.8 GiB RSS),
    # so the first identification request does not pay the cold load. Set false on small machines.
    recognition_preload: bool = True

    # Authorized 3D hide scans served to the 3D viewer (read-only). Empty => feature disabled.
    # Each sub-directory holding a .obj (+ optional .mtl and textures) is one scan.
    hide_scans_dir: str = ""
    # Scans are private and the API has no auth: by default only loopback clients
    # (Vite proxy, SSH tunnel) may download them.
    hide_scans_allow_remote: bool = False

    # Comma-separated list of allowed frontend origins
    cors_origins: str = "http://localhost:5173"

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, v: str) -> str:
        level = v.strip().upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid LOG_LEVEL {v!r}")
        return level

    @field_validator("cors_origins")
    @classmethod
    def _check_cors_origins(cls, v: str) -> str:
        # Credentials are allowed, so a wildcard origin would let any site make
        # authenticated requests. Origins must be listed explicitly.
        if "*" in v:
            raise ValueError("CORS_ORIGINS must list explicit origins; '*' is not allowed")
        return v

    @field_validator("gemini_timeout_seconds")
    @classmethod
    def _check_gemini_timeout(cls, v: float) -> float:
        if v <= 0 or v > 120:
            raise ValueError("GEMINI_TIMEOUT_SECONDS must be between 0 and 120")
        return v

    @field_validator("gemini_max_context_chars")
    @classmethod
    def _check_gemini_max_context_chars(cls, v: int) -> int:
        if v < 2000 or v > 200_000:
            raise ValueError("GEMINI_MAX_CONTEXT_CHARS must be between 2000 and 200000")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise postgres URLs so SQLAlchemy uses the psycopg (v3) driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
