from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://composegtfs:composegtfs@localhost:5432/composegtfs"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # JWT
    secret_key: str = ""
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # API docs
    docs_enabled: bool = False

    # CORS
    cors_origins: str = ""

    # Rate limiting
    login_rate_limit: str = "10/minute"

    # First superuser seed
    first_superuser: str = "admin"
    first_superuser_email: str = "admin@localhost.org"
    first_superuser_password: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        if not self.cors_origins:
            return []
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
