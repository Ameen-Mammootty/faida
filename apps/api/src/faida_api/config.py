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

    # Extraction (plan.md §5 layer 1; provider decision 2026-08-29, Decision
    # Log). "gemini" (Gemini 3 Flash) is the shipped default; "anthropic"
    # (Claude Opus 5) stays wired as the fallback, so the swap back is one env
    # var, no deploy. An empty key for the selected provider = no provider:
    # extract jobs fail into the §5 layer 6 path; upload + manual entry keep
    # working (M3).
    extraction_provider: str = "gemini"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    # C6 web API (M3). One shared-secret bearer token for the review screen;
    # empty refuses every /api request (fail closed, like the webhook secret).
    # Real auth arrives in M7.
    api_token: str = ""
    # The review screen's origin (apps/web), allowed through CORS.
    web_origin: str = "http://localhost:3000"

    worker_enabled: bool = True
    worker_poll_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
