from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://postgres:postgres@localhost:5432/faida"

    # Meta WhatsApp Cloud API
    meta_verify_token: str = "faida-verify"
    meta_app_secret: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    # v26.0 is the newest live Graph version (v27+ do not resolve, probed 2026-08-23).
    # Media download URLs expire fast, so an unsupported version fails ingest, not just replies.
    graph_api_base: str = "https://graph.facebook.com/v26.0"

    # Supabase Storage (service key never leaves the backend)
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "documents"

    # Extraction (plan.md §5 layer 1). Empty key = no provider: extract jobs
    # fail into the §5 layer 6 path; upload + manual entry keep working (M3).
    anthropic_api_key: str = ""

    worker_enabled: bool = True
    worker_poll_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
