from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.exceptions import FinApiException
from app.core.logging import logger
from app.core.database import close_database_engine
from app.core.redis import close_redis_client
from app.market.router import router as market_router
from app.portfolio.router import router as portfolio_router
from app.billing.router import router as billing_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting fin-api application lifespan...")
    yield
    logger.info("Shutting down fin-api application lifespan...")
    await close_redis_client()
    await close_database_engine()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="fin-api",
        description="Unified high-performance financial API & worker for Brazilian and international markets",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handler
    @app.exception_handler(FinApiException)
    async def fin_api_exception_handler(request: Request, exc: FinApiException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "message": exc.message, "detail": exc.detail},
        )

    # Health Check
    @app.get("/health", tags=["Health"])
    async def health_check():
        return {
            "status": "healthy",
            "service": "fin-api",
            "version": "0.1.0",
            "environment": settings.ENVIRONMENT,
        }

    # Mount Routers under /api/v1
    app.include_router(market_router, prefix="/api/v1")
    app.include_router(portfolio_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")

    return app


app = create_app()
