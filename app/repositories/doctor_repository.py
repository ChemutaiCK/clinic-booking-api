"""Data-access layer for Doctor entities."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.doctor import Doctor


class DoctorRepository:
    """Encapsulates all direct database access for the Doctor model."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, doctor_id: int) -> Doctor | None:
        return await self.db.get(Doctor, doctor_id)

    async def get_by_id_locked(self, doctor_id: int) -> Doctor | None:
        """
        Fetch a doctor row WITH a row-level lock (SELECT ... FOR UPDATE).

        Used by the booking/reschedule flow: locking the doctor row gives us
        a serialization point so that two concurrent booking requests for
        the SAME doctor cannot both pass the "is this slot free" check
        before either commits. See AppointmentService.book_appointment for
        the full explanation of this concurrency strategy.
        """
        stmt = select(Doctor).where(Doctor.id == doctor_id).with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Doctor]:
        result = await self.db.execute(select(Doctor).order_by(Doctor.id))
        return list(result.scalars().all())

    async def create(self, doctor: Doctor) -> Doctor:
        self.db.add(doctor)
        await self.db.flush()
        await self.db.refresh(doctor)
        return doctor
