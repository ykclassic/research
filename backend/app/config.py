from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    quote_cache_seconds: int = 30
    stale_quote_seconds: int = 180
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3

    twelve_data_api_key: str = ""

    # Authentication
    auth_database_path: str = "./data/auth.db"
    auth_session_seconds: int = 604800

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
