"""Application settings, read from environment variables (or a .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    app_name: str = "DigiPlus Context Hub"
    env: str = os.getenv("APP_ENV", "development")

    # Database: SQLite locally, PostgreSQL in production (DATABASE_URL from Neon/Render/Supabase).
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'digiplus.db'}")

    # AI provider: "gemini" | "anthropic" | "openai" | "none". Auto-detected from available keys if unset.
    ai_provider: str = os.getenv("AI_PROVIDER", "").lower()
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    ai_timeout_seconds: float = float(os.getenv("AI_TIMEOUT_SECONDS", "30"))
    ai_max_retries: int = int(os.getenv("AI_MAX_RETRIES", "1"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file: str = os.getenv("LOG_FILE", str(BASE_DIR / "logs" / "app.log"))

    # Static frontend build directory (served by FastAPI in production)
    static_dir: str = os.getenv("STATIC_DIR", str(BASE_DIR / "static"))

    seed_on_start: bool = os.getenv("SEED_ON_START", "true").lower() == "true"

    def resolved_provider(self) -> str:
        if self.ai_provider:
            return self.ai_provider
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        if self.openai_api_key:
            return "openai"
        return "none"


settings = Settings()

# Render/Heroku give "postgres://" URLs; SQLAlchemy needs the psycopg driver name.
if settings.database_url.startswith("postgres://"):
    settings.database_url = settings.database_url.replace("postgres://", "postgresql+psycopg://", 1)
elif settings.database_url.startswith("postgresql://"):
    settings.database_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
