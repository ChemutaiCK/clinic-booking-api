"""
Async SQLAlchemy engine and session management.

A single engine is created per process and reused across requests. Sessions
are created per-request via the `get_db` dependency (see
app/dependencies/database.py) so each request gets an isolated transactional
scope.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

settings = get_settings()

_engine_kwargs = dict(
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
)

# SQLite (used in tests) does not support pool_size/max_overflow the same way
# as PostgreSQL's QueuePool, so we only pass those for non-sqlite URLs.
if "sqlite" not in settings.DATABASE_URL:
    _engine_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
    _engine_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW

engine: AsyncEngine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a database session, guaranteeing cleanup on exit."""
    async with AsyncSessionLocal() as session:
        yield session
