"""Doctor model: represents a clinician with fixed working hours."""

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment


class Doctor(TimestampMixin, Base):
    """
    A clinic doctor.

    Working hours (work_start / work_end) are stored as naive `time` values
    that represent the clinic's LOCAL time-of-day (e.g. a doctor works
    09:00-17:00 every day, regardless of calendar date). Slot times on
    appointments, by contrast, are stored as full UTC datetimes. See the
    README "Timezone Strategy" section for the full reasoning: working hours
    are a recurring daily schedule, not a single instant, so they are
    intentionally modeled differently from appointment timestamps.
    """

    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    specialization: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    work_start: Mapped[time] = mapped_column(Time, nullable=False)
    work_end: Mapped[time] = mapped_column(Time, nullable=False)

    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="doctor",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Doctor id={self.id} name={self.full_name!r}>"
