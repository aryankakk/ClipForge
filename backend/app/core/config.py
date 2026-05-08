from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "TwitchClipper"
    DEBUG: bool = False
    SECRET_KEY: str = "change-this-in-production"
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://clipper:clipper@postgres:5432/twitchclipper"
    DATABASE_POOL_SIZE: int = 10

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Twitch
    TWITCH_CLIENT_ID: str
    TWITCH_CLIENT_SECRET: str
    TWITCH_WEBHOOK_SECRET: str = "twitch-webhook-secret"
    TWITCH_REDIRECT_URI: str = "http://localhost:8000/api/auth/callback"

    # OpenAI (for Whisper + GPT scoring)
    OPENAI_API_KEY: Optional[str] = None

    # Deepgram (alternative STT)
    DEEPGRAM_API_KEY: Optional[str] = None

    # Storage
    CLIPS_DIR: str = "/app/clips"
    PROCESSED_DIR: str = "/app/processed"

    # Highlight scoring thresholds
    CLIP_SCORE_THRESHOLD: float = 60.0
    SCORE_WINDOW_SECONDS: int = 30
    COOLDOWN_SECONDS: int = 90  # Min time between clips

    # Chat monitoring
    CHAT_VELOCITY_WINDOW: int = 10  # seconds
    CHAT_SPIKE_MULTIPLIER: float = 3.0  # x above baseline = spike

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()
