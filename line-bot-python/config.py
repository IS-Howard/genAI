"""
Configuration management for Line Bot
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""

    # Line Bot
    line_channel_secret: str
    line_channel_access_token: str

    # Database
    database_url: Optional[str] = None
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "line_bot"
    db_user: str = "postgres"
    db_password: str = ""

    # Google Gemini
    gemini_api_key: str
    gemini_model: str = "gemini-2.0-flash-exp"

    # App Settings
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"

    # Limits
    max_history_items: int = 50
    max_ai_context_items: int = 20
    max_files_per_group: int = 2

    # Optional
    train_booker_image: str = "train-booker"

    @property
    def db_url(self) -> str:
        """Get database URL"""
        if self.database_url:
            return self.database_url
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
