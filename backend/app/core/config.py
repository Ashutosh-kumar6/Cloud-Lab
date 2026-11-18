from typing import Annotated
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg2://cloudlab:cloudlab_pw@localhost:5432/cloudlab"
    redis_url: str = "redis://localhost:6379/0"
    # No hardcoded secret default: must be provided via environment variable
    jwt_secret: str = ""
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_use_vertex: bool = False
    environment: str = "development"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    idle_timeout_minutes: int = 30

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def validate_security(self) -> "Settings":
        # Disallow wildcard CORS
        if "*" in self.allowed_origins:
            raise ValueError("CORS cannot allow '*' as credentials are enabled.")

        # Validate JWT secret
        if self.environment.lower() == "testing":
            if not self.jwt_secret:
                self.jwt_secret = "test-secret-key-that-is-at-least-32-characters-long"
        elif self.environment.lower() == "production":
            if not self.jwt_secret or self.jwt_secret == "change-me-later" or len(self.jwt_secret) < 32:
                raise ValueError("JWT_SECRET must be set via environment variable to a strong secret (min 32 chars) in production.")
        else:
            if not self.jwt_secret or self.jwt_secret == "change-me-later":
                raise ValueError("JWT_SECRET must be set via environment variable with no hardcoded default.")

        return self


settings = Settings()
