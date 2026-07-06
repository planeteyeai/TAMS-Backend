"""
Core configuration module for TAMS Backend
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Application settings from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
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
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/tams"
    DATABASE_ECHO: bool = False
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 0
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_TTL: int = 3600
    
    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_S3_BUCKET: str = "tams-imagery"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,*"
    
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
    ENABLE_CDSE_STAC: bool = True


settings = Settings()
