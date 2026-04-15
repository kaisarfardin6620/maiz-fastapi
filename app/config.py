from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "maiz"
    MONGODB_MAX_POOL_SIZE: int = 100
    MONGODB_MIN_POOL_SIZE: int = 5
    MONGODB_SERVER_SELECTION_TIMEOUT_MS: int = 5000

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    APP_ENV: str = "development"
    DEBUG: bool = False
    CORS_ALLOW_ORIGINS: List[str] =[]

    OPENAI_API_KEY: str
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_VISION_MODEL: str = "gpt-4o"
    OPENAI_TRANSCRIBE_MODEL: str = "whisper-1"
    OPENAI_TIMEOUT_SECONDS: int = 30

    GOOGLE_MAPS_API_KEY: str
    GOOGLE_MAPS_TIMEOUT_SECONDS: int = 10

    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_BUCKET_NAME: str = "maiz-media"
    
    REDIS_URI: str = "redis://redis:6379/0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("CORS_ALLOW_ORIGINS", mode="before")
    @classmethod
    def parse_cors_allow_origins(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            return[item.strip() for item in value.split(",") if item.strip()]
        return value

settings = Settings()