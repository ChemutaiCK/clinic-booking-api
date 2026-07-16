"""
Appointment service: all booking/cancellation/reschedule business logic.

CONCURRENCY STRATEGY (read this before touching book_appointment or
reschedule_appointment)
---------------------------------------------------------------------------
The naive implementation - "check if the slot is free, then insert" - is a
classic TOCTOU (time-of-check to time-of-use) race condition: two concurrent
requests can both read "not booked" before either has committed its insert,
resulting in two BOOKED rows for the same doctor/slot.

We close this race with two layers, deliberately redundant:

1. Row lock (SELECT ... FOR UPDATE) on the Doctor row at the start of the
   transaction. PostgreSQL will block the second concurrent transaction at
   the lock acquisition step until the first transaction commits or rolls
   back. This means the "check availability, then insert" sequence for a
   given doctor is effectively serialized - the second request only
   proceeds with its availability check AFTER the first request's booking
   has already been committed, so it correctly sees the slot as taken.

2. Partial unique DB constraint on (doctor_id, slot_time) WHERE status =
   'BOOKED' (see app/models/appointment.py). This is the true source of
   truth and the last line of defense: even if the row lock were somehow
   bypassed (e.g. a raw script hitting the DB directly, a future bug that
   removes the lock), the database itself cannot physically store two
   BOOKED rows for the same doctor and slot. If that happens, the INSERT
   raises an IntegrityError, which we catch and translate into a clean
   SlotNotAvailableError (409).

We lock the DOCTOR row (not the slot_time row, since it may not exist yet)
because SELECT ... FOR UPDATE requires an existing row to lock. Locking the
parent doctor row serializes all booking attempts for that doctor, which is
an acceptable trade-off at clinic scale (a handful of doctors, each not
booked hyper-concurrently) - see README "Concurrency Strategy" for the
scalability discussion of this choice versus advisory locks.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.core.exceptions import (
    AppointmentAlreadyCancelledError,
    AppointmentNotFoundError,
    DoctorNotFoundError,
    InvalidSlotAlignmentError,
    OutsideWorkingHoursError,
    PatientNotFoundError,
    SlotInPastError,
    SlotNotAvailableError,
    SlotTooSoonError,
)
from app.core.logging import get_logger
from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.doctor_repository import DoctorRepository
from app.repositories.patient_repository import PatientRepository

logger = get_logger("app.services.appointment")
settings = get_settings()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppointmentService:
    """Orchestrates appointment booking, cancellation, and rescheduling."""

    def __init__(
        self,
        db: AsyncSession,
        doctor_repo: DoctorRepository,
        patient_repo: PatientRepository,
        appointment_repo: AppointmentRepository,
    ):
        self.db = db
        self.doctor_repo = doctor_repo
        self.patient_repo = patient_repo
        self.appointment_repo = appointment_repo

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_slot_shape(self, doctor: Doctor, slot_time: datetime, *, now: datetime) -> None:
        """
        Validate that slot_time is well-formed and legal, independent of
        whether it's currently booked. Raises the specific domain exception
        for the first rule violated, in the order the assessment lists them.
        """
        if slot_time < now:
            raise SlotInPastError()

        min_lead = now + timedelta(minutes=settings.MIN_BOOKING_LEAD_MINUTES)
        if slot_time < min_lead:
            raise SlotTooSoonError()

        slot_end = slot_time + timedelta(minutes=settings.SLOT_DURATION_MINUTES)
        if slot_time.time() < doctor.work_start or slot_end.time() > doctor.work_end:
            raise OutsideWorkingHoursError()

        # Slot must align to a 30-minute grid anchored at the doctor's work_start.
        work_start_dt = datetime.combine(slot_time.date(), doctor.work_start, tzinfo=slot_time.tzinfo)
        delta_minutes = (slot_time - work_start_dt).total_seconds() / 60
        if delta_minutes < 0 or delta_minutes % settings.SLOT_DURATION_MINUTES != 0:
            raise InvalidSlotAlignmentError()

    async def _get_doctor_or_404(self, doctor_id: int) -> Doctor:
        doctor = await self.doctor_repo.get_by_id(doctor_id)
        if doctor is None:
            raise DoctorNotFoundError()
        return doctor

    # ------------------------------------------------------------------
    # Booking
    # ------------------------------------------------------------------

    async def book_appointment(self, doctor_id: int, patient_id: int, slot_time: datetime) -> Appointment:
        now = _utcnow()

        # Validate existence of referenced entities first (cheap, no lock needed yet).
        patient = await self.patient_repo.get_by_id(patient_id)
        if patient is None:
            raise PatientNotFoundError()

        doctor_unlocked = await self.doctor_repo.get_by_id(doctor_id)
        if doctor_unlocked is None:
            raise DoctorNotFoundError()

        try:
            # Acquire the row lock BEFORE checking availability. Everything
            # from here to commit executes as a single serialized unit per
            # doctor - see module docstring for the full rationale.
            doctor = await self.doctor_repo.get_by_id_locked(doctor_id)
            if doctor is None:
                raise DoctorNotFoundError()

            self._validate_slot_shape(doctor, slot_time, now=now)

            if await self.appointment_repo.is_slot_booked(doctor_id, slot_time):
                raise SlotNotAvailableError()

            appointment = Appointment(
                doctor_id=doctor_id,
                patient_id=patient_id,
                slot_time=slot_time,
                status=AppointmentStatus.BOOKED,
            )
            appointment = await self.appointment_repo.create(appointment)
            await self.db.commit()
            logger.info(
                "Booked appointment id=%s doctor_id=%s patient_id=%s slot_time=%s",
                appointment.id,
                doctor_id,
                patient_id,
                slot_time.isoformat(),
            )
            return appointment

        except IntegrityError:
            # Final safety net: the DB-level partial unique constraint caught
            # a race that slipped past the application-level lock/check
            # (e.g. a concurrent transaction outside this lock's scope).
            await self.db.rollback()
            logger.warning(
                "IntegrityError booking doctor_id=%s slot_time=%s - slot taken concurrently",
                doctor_id,
                slot_time.isoformat(),
            )
            raise SlotNotAvailableError() from None
        except Exception:
            await self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------

    async def cancel_appointment(self, appointment_id: int, cancellation_reason: str) -> Appointment:
        try:
            appointment = await self.appointment_repo.get_by_id_locked(appointment_id)
            if appointment is None:
                raise AppointmentNotFoundError()

            if appointment.status == AppointmentStatus.CANCELLED:
                raise AppointmentAlreadyCancelledError()

            appointment.status = AppointmentStatus.CANCELLED
            appointment.cancellation_reason = cancellation_reason
            await self.db.flush()
            await self.db.commit()
            await self.db.refresh(appointment)
            logger.info("Cancelled appointment id=%s", appointment_id)
            return appointment
        except Exception:
            await self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Reschedule
    # ------------------------------------------------------------------

    async def reschedule_appointment(self, appointment_id: int, new_slot_time: datetime) -> Appointment:
        """
        Move an appointment to a new slot atomically.

        We update the SAME appointment row's slot_time in place (rather than
        cancelling the old row and creating a new one) inside a single
        transaction. This means "free the old slot" and "reserve the new
        slot" happen as one atomic operation from the database's point of
        view: either the row lands on the new slot_time and the old
        slot_time no longer has any BOOKED row referencing it, or (if
        validation fails, or the new slot is taken) the whole transaction
        rolls back and the appointment stays exactly where it was - the
        patient never loses their original slot.
        """
        now = _utcnow()
        try:
            appointment = await self.appointment_repo.get_by_id_locked(appointment_id)
            if appointment is None:
                raise AppointmentNotFoundError()

            if appointment.status == AppointmentStatus.CANCELLED:
                raise AppointmentAlreadyCancelledError()

            # Lock the doctor row too, for the same reason as book_appointment:
            # serialize concurrent booking/reschedule attempts for this doctor.
            doctor = await self.doctor_repo.get_by_id_locked(appointment.doctor_id)
            if doctor is None:
                raise DoctorNotFoundError()

            self._validate_slot_shape(doctor, new_slot_time, now=now)

            if new_slot_time != appointment.slot_time and await self.appointment_repo.is_slot_booked(
                appointment.doctor_id, new_slot_time
            ):
                raise SlotNotAvailableError()

            appointment.slot_time = new_slot_time
            await self.db.flush()
            await self.db.commit()
            await self.db.refresh(appointment)
            logger.info(
                "Rescheduled appointment id=%s to slot_time=%s",
                appointment_id,
                new_slot_time.isoformat(),
            )
            return appointment

        except IntegrityError:
            await self.db.rollback()
            logger.warning(
                "IntegrityError rescheduling appointment id=%s to slot_time=%s - taken concurrently",
                appointment_id,
                new_slot_time.isoformat(),
            )
            raise SlotNotAvailableError() from None
        except Exception:
            await self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    async def get_availability(self, doctor_id: int, target_date) -> list[datetime]:
        doctor = await self._get_doctor_or_404(doctor_id)

        all_slots: list[datetime] = []
        cursor = datetime.combine(target_date, doctor.work_start, tzinfo=timezone.utc)
        work_end_dt = datetime.combine(target_date, doctor.work_end, tzinfo=timezone.utc)
        step = timedelta(minutes=settings.SLOT_DURATION_MINUTES)

        while cursor + step <= work_end_dt:
            all_slots.append(cursor)
            cursor += step

        booked = set(await self.appointment_repo.list_booked_slots_for_date(doctor_id, target_date))
        now = _utcnow()
        min_lead = now + timedelta(minutes=settings.MIN_BOOKING_LEAD_MINUTES)

        available = [slot for slot in all_slots if slot not in booked and slot >= min_lead]
        return available

    # ------------------------------------------------------------------
    # Patient appointment history
    # ------------------------------------------------------------------

    async def get_appointment(self, appointment_id: int) -> Appointment:
        appointment = await self.appointment_repo.get_by_id(appointment_id)
        if appointment is None:
            raise AppointmentNotFoundError()
        return appointment

    async def list_upcoming_for_patient(self, patient_id: int) -> list[Appointment]:
        patient = await self.patient_repo.get_by_id(patient_id)
        if patient is None:
            raise PatientNotFoundError()
        return await self.appointment_repo.list_upcoming_for_patient(patient_id, _utcnow())
