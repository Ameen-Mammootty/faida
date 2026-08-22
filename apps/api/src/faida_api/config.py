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
    graph_api_base: str = "https://graph.facebook.com/v21.0"

    # Supabase Storage (service key never leaves the backend)
    supabase_url: str = ""
    supabase_service_key: str = ""
    storage_bucket: str = "documents"

    worker_enabled: bool = True
    worker_poll_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
