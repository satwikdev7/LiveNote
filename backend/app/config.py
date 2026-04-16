from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "LiveNote Backend"
    app_env: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    frontend_origin: str = "http://localhost:3000"
    reconnect_timeout_sec: int = 300
    concurrent_meetings: int = 1

    diarization_enabled: bool = True
    diarization_mode: str = "async_backfill"
    asr_chunk_sec: int = 15
    whisper_model_size: str = "base"
    browser_target: str = "chrome"
    llm_window_chunks: int = 4
    llm_window_sec: int = 60
    live_intelligence_enabled: bool = True
    llm_provider: str = "deepseek"
    deepseek_model: str = "deepseek-chat"
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    llm_max_retries: int = 3
    llm_failure_mode: str = "queue_and_merge"
    huggingface_token: str | None = None
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None
    supabase_storage_bucket: str = "meeting-exports"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
