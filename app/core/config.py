"""
Core configuration module for TAMS Backend
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env regardless of process cwd
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR / ".env"


class Settings(BaseSettings):
    """Application settings from environment variables"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    
    # App
    APP_NAME: str = "TAMS - Transmission Asset Intelligence Platform"
    APP_DESCRIPTION: str = "AI-Powered Transmission Asset Monitoring"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    
    # Database — Railway: set DATABASE_URL=${{Postgres.DATABASE_URL}}
    # (postgres://… is auto-normalized to postgresql+asyncpg://)
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/tams"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 5
    DATABASE_MAX_OVERFLOW: int = 5

    # When Postgres is empty, import indian_KML into the database on startup
    IMPORT_KML_ON_STARTUP: bool = True
    IMPORT_INCLUDE_TOWERS: bool = True
    IMPORT_BATCH_SIZE: int = 500
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = 3600
    
    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = "tams-imagery"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # CORS — include your Render frontend URL in production
    CORS_ORIGINS: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "https://tams-txmr.onrender.com,https://tams-28nc.onrender.com"
    )
    # Railway / Render hosts; keep * so platform domains always work
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,*,.up.railway.app,.onrender.com"
    
    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 1
    
    # Pagination
    DEFAULT_PAGE_SIZE: int = 100
    MAX_PAGE_SIZE: int = 1000
    
    # ML
    MODEL_CACHE_DIR: str = "./models"
    ENABLE_ML_FEATURES: bool = True

    # Copernicus Data Space (Sentinel-2 Night Campaign)
    CDSE_STAC_URL: str = "https://stac.dataspace.copernicus.eu/v1"
    CDSE_NIGHT_COLLECTION: str = "sentinel-2-night-time-acquisitions"
    CDSE_S3_BUCKET: str = "eodata"
    CDSE_S3_NIGHT_PREFIX: str = "Sentinel-2/MSI/S2MSI_NIGHT"
    CDSE_S3_ENDPOINT: str = "https://eodata.dataspace.copernicus.eu"
    CDSE_S3_ACCESS_KEY: Optional[str] = None
    CDSE_S3_SECRET_KEY: Optional[str] = None
    ENABLE_CDSE_STAC: bool = False


settings = Settings()
