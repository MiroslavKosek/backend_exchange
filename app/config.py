"""Application configuration models and settings loading order."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

class LoggingConfig(BaseModel):
    """Logging-related configuration values."""

    level: str = "INFO"
    filename: str = "logs/app.log"
    max_bytes: int = 5_242_880
    backup_count: int = 3


class Settings(BaseSettings):
    """Main application settings loaded from env and JSON sources."""

    model_config = SettingsConfigDict(
        env_file=".env",
        json_file="config.json",
    )

    api_url: str
    logging: LoggingConfig = LoggingConfig()
    environment: str = "development"

    admin_username: str
    admin_password: str
    jwt_secret_key: str

    @classmethod
    # Required signature by pydantic-settings custom source hook.
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            JsonConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


settings = Settings()
