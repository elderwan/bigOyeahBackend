from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FitBooking API"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False
    database_url: str = Field(
        default="mysql+aiomysql://fitbooking_app:change_me@127.0.0.1:3306/fitbooking"
    )
    ddl_database_url: str = Field(
        default="mysql+aiomysql://fitbooking_ddl:change_me@127.0.0.1:3306/fitbooking"
    )
    timezone: str = "Asia/Bangkok"
    cors_origins: list[str] = ["http://localhost:3000"]
    sql_echo: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
