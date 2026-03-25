from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI: str
    MONGODB_DB_NAME: str = "maiz"

    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"

    APP_ENV: str = "development"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()