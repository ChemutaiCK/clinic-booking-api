"""Reusable SQLAlchemy model mixins."""

from datetime import datetime, timezone

from sqlalchemy.orm import Mapped, mapped_column

from app.database.types import UTCDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds created_at / updated_at columns, always stored in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=_utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
