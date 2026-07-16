"""Data-access layer for Appointment entities."""

from datetime import date, datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.appointment import Appointment, AppointmentStatus


class AppointmentRepository:
    """Encapsulates all direct database access for the Appointment model."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, appointment_id: int) -> Appointment | None:
        return await self.db.get(Appointment, appointment_id)

    async def get_by_id_locked(self, appointment_id: int) -> Appointment | None:
        """Fetch an appointment WITH a row lock, for cancel/reschedule flows."""
        stmt = select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def is_slot_booked(self, doctor_id: int, slot_time: datetime) -> bool:
        """
        Check whether a doctor already has an active (BOOKED) appointment at
        this exact slot_time.

        NOTE: this check alone is NOT sufficient to prevent double-booking
        under concurrency - see AppointmentService for why the doctor row is
        locked before this check runs, and why the database also enforces a
        partial unique index as a final safety net.
        """
        stmt = select(Appointment.id).where(
            Appointment.doctor_id == doctor_id,
            Appointment.slot_time == slot_time,
            Appointment.status == AppointmentStatus.BOOKED,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def list_booked_slots_for_date(self, doctor_id: int, target_date: date) -> list[datetime]:
        """Return all BOOKED slot_times for a doctor on a given UTC calendar date."""
        day_start = datetime.combine(target_date, time.min, tzinfo=timezone.utc)
        day_end = datetime.combine(target_date, time.max, tzinfo=timezone.utc)
        stmt = select(Appointment.slot_time).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == AppointmentStatus.BOOKED,
            Appointment.slot_time >= day_start,
            Appointment.slot_time <= day_end,
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_upcoming_for_patient(self, patient_id: int, now: datetime) -> list[Appointment]:
        """Return a patient's upcoming BOOKED appointments, soonest first."""
        stmt = (
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == AppointmentStatus.BOOKED,
                Appointment.slot_time >= now,
            )
            .order_by(Appointment.slot_time.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, appointment: Appointment) -> Appointment:
        self.db.add(appointment)
        await self.db.flush()
        await self.db.refresh(appointment)
        return appointment
