"""
Shared pytest fixtures.

Tests run against a temporary file-based SQLite database (not the
production PostgreSQL database) so the suite is fast and has zero external
dependencies. SQLite is configured with a busy_timeout so that concurrent
writers wait for each other instead of failing immediately - this lets the
concurrency test genuinely exercise the same "lock, check, insert" code
path that runs against PostgreSQL in production. The database-level partial
unique index (the real source of truth for preventing double-booking) is
created identically on both backends.

Note: SQLite silently ignores `SELECT ... FOR UPDATE` (it has no row-level
locking), so the row-lock layer of the concurrency strategy isn't exercised
by this suite - but the partial unique index safety net is, which is
sufficient to prove no double-booking can occur end-to-end.
"""

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import date, datetime, time, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ["ENVIRONMENT"] = "test"
os.environ["LOG_JSON"] = "false"

from app.database.base import Base  # noqa: E402
from app.dependencies.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402
from app.models.patient import Patient  # noqa: E402


@pytest_asyncio.fixture
async def db_engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(url, connect_args={"timeout": 30})

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()
    os.remove(path)


@pytest_asyncio.fixture
async def session_factory(db_engine):
    return async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_doctor(session_factory) -> Doctor:
    async with session_factory() as session:
        doctor = Doctor(
            full_name="Dr. Test Doctor",
            specialization="General Practice",
            email="test.doctor@clinic.example",
            work_start=time(9, 0),
            work_end=time(17, 0),
        )
        session.add(doctor)
        await session.commit()
        await session.refresh(doctor)
        return doctor


@pytest_asyncio.fixture
async def seeded_patient(session_factory) -> Patient:
    async with session_factory() as session:
        patient = Patient(full_name="Test Patient", email="test.patient@example.com")
        session.add(patient)
        await session.commit()
        await session.refresh(patient)
        return patient


@pytest_asyncio.fixture
async def wide_hours_doctor(session_factory) -> Doctor:
    """A doctor with near-all-day hours, used to isolate the 1-hour lead-time
    rule from the working-hours rule in tests."""
    async with session_factory() as session:
        doctor = Doctor(
            full_name="Dr. Wide Hours",
            specialization="Urgent Care",
            email="wide.hours@clinic.example",
            work_start=time(0, 0),
            work_end=time(23, 30),
        )
        session.add(doctor)
        await session.commit()
        await session.refresh(doctor)
        return doctor


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    app.dependency_overrides.clear()


def future_slot(days_ahead: int = 1, hour: int = 9, minute: int = 0) -> datetime:
    """Build a slot_time far enough in the future to pass the 1-hour lead-time rule."""
    target = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    return target.replace(hour=hour, minute=minute, second=0, microsecond=0)


def ceil_to_grid(dt: datetime, step_minutes: int = 30) -> datetime:
    """
    Round dt UP to the next slot boundary on a `step_minutes` grid anchored
    at midnight. Used to deterministically build a slot that is always in
    the future but always less than one grid-step away from `dt` - i.e.
    always inside the "too soon to book" window when step < the lead time.
    """
    dt = dt.replace(second=0, microsecond=0)
    total_minutes = dt.hour * 60 + dt.minute
    remainder = total_minutes % step_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=step_minutes - remainder)
