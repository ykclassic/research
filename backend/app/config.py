from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1,testserver"

    quote_cache_seconds: int = 30
    stale_quote_seconds: int = 180
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3

    twelve_data_api_key: str = ""

    # Supabase Auth
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    auth_session_seconds: int = 604800
    auth_password_reset_redirect_url: str = "http://localhost:5173/?reset=1"

    # CSRF signing secret. Set a long random value in production.
    csrf_secret: str = "development-only-change-me"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.app_env.lower() != "production":
            return self

        if self.csrf_secret == "development-only-change-me" or len(self.csrf_secret) < 32:
            raise ValueError(
                "Production requires a non-default CSRF_SECRET of at least 32 characters."
            )

        origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
        if not origins:
            raise ValueError("Production requires at least one configured CORS origin.")
        if not any(not origin.startswith(("http://localhost", "http://127.0.0.1")) for origin in origins):
            raise ValueError("Production CORS origins must include a non-localhost origin.")

        if not self.twelve_data_api_key.strip():
            raise ValueError("Production requires TWELVE_DATA_API_KEY.")
        if not self.supabase_url.strip() or not self.supabase_publishable_key.strip():
            raise ValueError("Production requires Supabase URL and publishable key.")
        if self.auth_password_reset_redirect_url.startswith(
            ("http://localhost", "http://127.0.0.1")
        ):
            raise ValueError("Production password-reset redirect must not use localhost.")

        hosts = [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]
        if not hosts:
            # The current Render deployment is covered by the secure default.
            # Custom production domains should set TRUSTED_HOSTS explicitly.
            self.trusted_hosts = "research-76vr.onrender.com"
        elif not any(
            host not in {"localhost", "127.0.0.1", "testserver"}
            for host in hosts
        ):
            raise ValueError(
                "Production TRUSTED_HOSTS must include a non-localhost host."
            )

        return self


settings = Settings()
