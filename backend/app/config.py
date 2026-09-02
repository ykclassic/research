from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    trusted_hosts: str = "localhost,127.0.0.1,testserver,research-76vr.onrender.com"

    quote_cache_seconds: int = 30
    stale_quote_seconds: int = 180
    market_cache_stale_seconds: int = 900
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3
    analysis_timeout_seconds: float = 10.0
    provider_timeout_seconds: float = 5.0
    provider_failure_threshold: int = 3
    provider_circuit_cooldown_seconds: int = 60

    twelve_data_api_key: str = ""
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""

    # Supabase Auth
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    auth_session_seconds: int = 604800
    auth_password_reset_redirect_url: str = "http://localhost:5173/?reset=1"

    # CSRF signing secret. Set a long random value in production.
    csrf_secret: str = "development-only-change-me"

    # GitHub Actions OIDC trust for server-to-server production verification.
    # Multiple explicitly trusted verification workflows are supported.
    github_oidc_issuer: str = "https://token.actions.githubusercontent.com"
    github_oidc_jwks_url: str = "https://token.actions.githubusercontent.com/.well-known/jwks"
    github_oidc_audience: str = "research-production-verifier"
    github_oidc_repository: str = "ykclassic/research"
    github_oidc_workflows: str = (
        ".github/workflows/production-regime-verification.yml,"
        ".github/workflows/production-market-data-verification.yml"
    )
    github_oidc_ref: str = "refs/heads/main"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def trusted_oidc_workflows(self) -> tuple[str, ...]:
        return tuple(
            item.strip()
            for item in self.github_oidc_workflows.split(",")
            if item.strip()
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
            raise ValueError("Production requires at least one configured trusted host.")
        if not any(host not in {"localhost", "127.0.0.1", "testserver"} for host in hosts):
            raise ValueError("Production TRUSTED_HOSTS must include a non-localhost host.")

        if self.analysis_timeout_seconds <= 0 or self.provider_timeout_seconds <= 0:
            raise ValueError("Production request timeouts must be greater than zero.")
        if self.provider_failure_threshold < 1:
            raise ValueError("Provider failure threshold must be at least one.")
        if self.provider_circuit_cooldown_seconds <= 0:
            raise ValueError("Provider circuit cooldown must be greater than zero.")

        if not self.github_oidc_audience.strip():
            raise ValueError("Production requires GITHUB_OIDC_AUDIENCE.")
        if self.github_oidc_repository != "ykclassic/research":
            raise ValueError("Production GitHub OIDC repository must be ykclassic/research.")
        if self.github_oidc_ref != "refs/heads/main":
            raise ValueError("Production GitHub OIDC verification must be restricted to main.")
        if not self.trusted_oidc_workflows:
            raise ValueError("Production requires at least one trusted GitHub OIDC workflow.")
        if any(not workflow.startswith(".github/workflows/") for workflow in self.trusted_oidc_workflows):
            raise ValueError("Production GitHub OIDC workflows must be repository workflow paths.")

        return self


settings = Settings()
