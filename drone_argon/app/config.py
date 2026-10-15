#
# FILE: app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Autonomous Drone Architect"
    VERSION: str = "1.0.0"
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:password@localhost/drone_db")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "supersecretkey")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # External Services
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY")
    GOOGLE_SEARCH_ENGINE_ID: str = os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    
    # Celery / Redis
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

settings = Settings()