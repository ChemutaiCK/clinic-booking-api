"""
Portable timezone-aware datetime column type.

PostgreSQL's TIMESTAMPTZ round-trips timezone-aware datetimes correctly on
its own. SQLite has no native timezone-aware datetime type - SQLAlchemy's
plain `DateTime(timezone=True)` silently degrades to naive datetimes on
SQLite, which would cause two problems: (1) naive vs. aware comparison
errors in application code, and (2) inconsistent JSON serialization
(missing UTC offset) depending on which database is in use.

`UTCDateTime` normalizes this: on the way into the database it always
stores a naive UTC value (converting first if the incoming value carries a
different timezone), and on the way out it always re-attaches UTC tzinfo.
This guarantees identical behavior in production (PostgreSQL) and in the
test suite (SQLite), which is precisely what we want since our tests are
asserting on this exact behavior.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Stores naive UTC in the database; always returns UTC-aware datetimes in Python."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
