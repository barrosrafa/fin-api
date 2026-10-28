from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.exceptions import FinApiException
from app.core.logging import logger
from app.core.database import close_database_engine, get_async_session
from app.core.redis import close_redis_client, get_redis_client
from sqlalchemy import text
from app.auth.router import router as auth_router
from app.market.router import router as market_router
from app.portfolio.router import router as portfolio_router
from app.billing.router import router as billing_router
from app.fiis.router import router as fiis_router
from app.stocks.router import router as stocks_router
from app.funds.router import router as funds_router
from app.etfs.router import router as etfs_router
from app.derivatives.router import router as derivatives_router
from app.fixed_income.router import router as fixed_income_router
from app.screener.router import router as screener_router
from app.comparator.router import router as comparator_router
from app.intelligence.router import router as intelligence_router
from app.macro.router import router as macro_router
from app.analytics.router import router as analytics_router
from app.cms.router import router as cms_router
from app.suitability.router import router as suitability_router
from app.brokers.router import router as brokers_router
from app.simulator.router import router as simulator_router
from app.rankings.router import router as rankings_router
from app.portfolio.overrides import router as graph_router


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

    # CORS Configuration
    allowed_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://fin-web.vercel.app",
        "https://fin.com.br",
        "https://app.fin.com.br",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=r"^https:\/\/fin-web-[a-zA-Z0-9_-]+\.vercel\.app$" if settings.ENVIRONMENT != "production" else None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    )

    # Security Headers Middleware
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Global Exception Handler
    @app.exception_handler(FinApiException)
    async def fin_api_exception_handler(request: Request, exc: FinApiException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": True, "message": exc.message, "detail": exc.detail},
        )

    # Health & Readiness Probes
    @app.get("/live", tags=["Health"])
    @app.get("/health", tags=["Health"])
    async def liveness():
        return {
            "status": "healthy",
            "service": "fin-api",
            "version": "0.1.0",
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/ready", tags=["Health"])
    async def readiness():
        checks = {"database": False, "redis": False}
        try:
            from app.core.database import get_session_factory
            factory = get_session_factory()
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception as e:
            logger.error("Readiness probe database check failed", error=str(e))

        try:
            redis = await get_redis_client()
            if redis and await redis.ping():
                checks["redis"] = True
        except Exception as e:
            logger.error("Readiness probe redis check failed", error=str(e))

        is_ready = all(checks.values())
        status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
        return JSONResponse(
            status_code=status_code,
            content={"status": "ready" if is_ready else "not_ready", "checks": checks},
        )

    # Mount Routers under /api/v1
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(market_router, prefix="/api/v1")
    app.include_router(portfolio_router, prefix="/api/v1")
    app.include_router(billing_router, prefix="/api/v1")
    app.include_router(fiis_router, prefix="/api/v1")
    app.include_router(stocks_router, prefix="/api/v1")
    app.include_router(funds_router, prefix="/api/v1")
    app.include_router(etfs_router, prefix="/api/v1")
    app.include_router(derivatives_router, prefix="/api/v1")
    app.include_router(fixed_income_router, prefix="/api/v1")
    app.include_router(screener_router, prefix="/api/v1")
    app.include_router(comparator_router, prefix="/api/v1")
    app.include_router(intelligence_router, prefix="/api/v1")
    app.include_router(macro_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(cms_router, prefix="/api/v1")
    app.include_router(suitability_router, prefix="/api/v1")
    app.include_router(brokers_router, prefix="/api/v1")
    app.include_router(simulator_router, prefix="/api/v1")
    app.include_router(rankings_router, prefix="/api/v1")
    app.include_router(graph_router)

    return app


app = create_app()
