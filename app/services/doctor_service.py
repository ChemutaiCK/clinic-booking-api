"""Doctor service: application logic for doctor management."""

from app.core.exceptions import DoctorNotFoundError
from app.models.doctor import Doctor
from app.repositories.doctor_repository import DoctorRepository
from sqlalchemy.ext.asyncio import AsyncSession


class DoctorService:
    def __init__(self, db: AsyncSession, doctor_repo: DoctorRepository):
        self.db = db
        self.doctor_repo = doctor_repo

    async def create_doctor(self, doctor: Doctor) -> Doctor:
        try:
            created = await self.doctor_repo.create(doctor)
            await self.db.commit()
            return created
        except Exception:
            await self.db.rollback()
            raise

    async def get_doctor(self, doctor_id: int) -> Doctor:
        doctor = await self.doctor_repo.get_by_id(doctor_id)
        if doctor is None:
            raise DoctorNotFoundError()
        return doctor

    async def list_doctors(self) -> list[Doctor]:
        return await self.doctor_repo.list_all()
