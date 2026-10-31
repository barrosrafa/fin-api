import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy import event, text
from sqlalchemy.orm import Session
from app.config import get_settings

# Never persist tenant settings at connection scope. Reapply after every commit/rollback.
TENANT_SQL = text("""
    SELECT set_config('app.current_user_id', COALESCE((
        SELECT id_usuario::text FROM core.usuario
        WHERE id_externo = :subject OR id_usuario::text = :subject
        LIMIT 1
    ), ''), true)
""")


class TenantSession(Session):
    pass


@event.listens_for(TenantSession, "after_begin")
def _apply_tenant(session, transaction, connection):
    subject = session.info.get("auth_subject")
    connection.execute(text("SELECT set_config('app.auth_subject', :subject, true), set_config('app.auth_email', :email, true)"),
                       {"subject": subject or "", "email": session.info.get("auth_email", "")})
    if subject:
        connection.execute(TENANT_SQL, {"subject": subject})
    else:
        connection.execute(text("SELECT set_config('app.current_user_id', '', true)"))


async def bind_tenant(session: AsyncSession, subject: str) -> None:
    session.info["auth_subject"] = subject
    # Authentication may already have opened a transaction (JIT sync/cache miss).
    await session.execute(text("SELECT set_config('app.auth_subject', :subject, true)"), {"subject": subject})
    await session.execute(TENANT_SQL, {"subject": subject})


async def bind_auth_email(session: AsyncSession, email: str) -> None:
    # Login/registration require one exact account before a tenant is authenticated.
    # This scoped context is transaction-local and is cleared with the session.
    normalized = email.lower().strip()
    session.info["auth_email"] = normalized
    await session.execute(text("SELECT set_config('app.auth_email', :email, true)"), {"email": normalized})


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None
_engine_loop: asyncio.AbstractEventLoop | None = None


def get_async_engine() -> AsyncEngine:
    global _engine, _sessionmaker, _engine_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if _engine is None or (_engine_loop is not None and _engine_loop != current_loop):
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,
            echo=False,
            hide_parameters=True,
        )
        _engine_loop = current_loop
        _sessionmaker = None
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    engine = get_async_engine()
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            sync_session_class=TenantSession,
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            session.info.pop("auth_subject", None)
            session.info.pop("auth_email", None)
            await session.close()


async def close_database_engine():
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
