"""
Appointment model.

CONCURRENCY DESIGN NOTE
------------------------
Double-booking is prevented at TWO layers, intentionally redundant:

1. Application layer: the booking service runs inside a transaction and
   takes a row lock (SELECT ... FOR UPDATE) on the doctor before checking
   availability and inserting, so concurrent requests for the same doctor
   serialize against each other.
2. Database layer: a PARTIAL UNIQUE INDEX on (doctor_id, slot_time) that
   only applies to rows with status = 'BOOKED'. This is the ultimate
   source of truth - even if the application-level lock were ever bypassed
   (e.g. a second process, a bug, a manual script), the database itself
   physically cannot hold two BOOKED rows for the same doctor and slot.

The index is partial (WHERE status = 'BOOKED') rather than a plain unique
constraint on (doctor_id, slot_time) because a CANCELLED appointment must
free up its slot for rebooking. A non-partial unique constraint would
permanently block that slot even after cancellation.
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Enum, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.database.types import UTCDateTime
from app.models.mixins import TimestampMixin

if TYPE_CHECKING:
    from app.models.doctor import Doctor
    from app.models.patient import Patient


class AppointmentStatus(str, enum.Enum):
    BOOKED = "BOOKED"
    CANCELLED = "CANCELLED"


class Appointment(TimestampMixin, Base):
    """
    A booked (or cancelled) 30-minute slot between a doctor and a patient.

    `slot_time` is always stored as a timezone-aware UTC datetime and marks
    the START of the 30-minute slot.
    """

    __tablename__ = "appointments"
    __table_args__ = (
        # Partial unique index: only one BOOKED appointment per doctor per slot_time.
        # Cancelled appointments are excluded, so the slot becomes bookable again.
        Index(
            "uq_doctor_slot_when_booked",
            "doctor_id",
            "slot_time",
            unique=True,
            postgresql_where=text("status = 'BOOKED'"),
            sqlite_where=text("status = 'BOOKED'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slot_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus, native_enum=False, length=20),
        nullable=False,
        default=AppointmentStatus.BOOKED,
        index=True,
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    doctor: Mapped["Doctor"] = relationship(back_populates="appointments")
    patient: Mapped["Patient"] = relationship(back_populates="appointments")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<Appointment id={self.id} doctor_id={self.doctor_id} "
            f"slot_time={self.slot_time.isoformat()} status={self.status}>"
        )
