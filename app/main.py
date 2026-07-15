"""
Main FastAPI Application Entry Point
TAMS - Transmission Asset Monitoring System
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.core.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events.
    """
    from app.db.init_db import init_database, is_db_ready

    logger.info("Application startup")
    db_ok = await init_database()
    if db_ok:
        logger.info("Database initialized and ready")
    else:
        logger.warning("Running in mock-data mode (no database)")
        from app.services.kml_loader import get_corridor_assets, preload_kml_assets
        import app.services.mock_data as mock_data

        preload_kml_assets()
        mock_data.MOCK_ASSETS.clear()
        mock_data.MOCK_ASSETS.extend(get_corridor_assets())
        mock_data.rebuild_derived_mock_data()
        logger.info("Loaded %d KML corridor assets (India)", len(mock_data.MOCK_ASSETS))
    app.state.database_enabled = is_db_ready()
    yield
    logger.info("Application shutdown")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        FastAPI: Configured application instance
    """
    
    app = FastAPI(
        title=settings.APP_NAME,
        description=settings.APP_DESCRIPTION,
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # CORS must allow the frontend origin(s). In dev, allow any localhost port;
    # in production, allow configured origins plus *.onrender.com / *.vercel.app.
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    cors_kwargs = {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
    if settings.DEBUG:
        cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"
    else:
        cors_kwargs["allow_origin_regex"] = (
            r"https://([a-z0-9-]+\.)*(onrender\.com|vercel\.app|railway\.app)"
        )

    app.add_middleware(CORSMiddleware, **cors_kwargs)

    # TrustedHost can block requests before CORS headers are applied
    if not settings.DEBUG:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[
                h.strip() for h in settings.ALLOWED_HOSTS.split(",") if h.strip()
            ],
        )
    
    # Include routers
    app.include_router(api_v1_router, prefix="/api/v1")
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": settings.APP_VERSION}
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }
    
    logger.info(f"Application {settings.APP_NAME} v{settings.APP_VERSION} created")
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    # Bind to the platform-assigned port (Railway/Render set $PORT).
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(settings.PORT),
        log_level=settings.LOG_LEVEL.lower(),
    )
