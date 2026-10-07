"""Centralized environment configuration for the merged FastAPI service.

All values that were hardcoded in the Java services, such as database URLs,
AI tokens, prompt paths, and UDP ports, are read from environment variables
or `.env` through this module.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with production-safe defaults where possible."""

    app_name: str = "python-lingjing-ai-server"
    app_host: str = "0.0.0.0"
    app_port: int = 9909

    # Main business database. The project now uses SQLite only.
    database_url: str = "sqlite:///./data/lingjing.db"
    # High-frequency realtime/stream data is separated into another SQLite file.
    stream_database_url: str = "sqlite:///./data/stream.db"
    database_echo: bool = False

    ai_base_url: str = "https://api.example.com/v1"
    ai_api_key: str = ""
    ai_chat_model: str = ""
    ai_analysis_model: str = ""
    
    
    ai_api_style: str = "openai"
    
    
    vision_upload_base_url: str = ""
    internal_ai_token: str = ""
    ai_timeout_seconds: int = 90

    ws_log_enabled: bool = True
    ws_log_file: str = "logs/websocket.log"
    ws_log_level: str = "INFO"
    ws_log_max_bytes: int = 50 * 1024 * 1024
    ws_log_backup_count: int = 5
    ws_log_body_max_chars: int = 12000

    prompt_dir: Path = Field(default=Path("app/prompts"))
    udp_target_host: str = "localhost"
    udp_target_port: int = 9876
    udp_server_port: int = 9877

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings object so dependencies share one config snapshot."""

    return Settings()
