"""Data-access layer for Patient entities."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient import Patient


class PatientRepository:
    """Encapsulates all direct database access for the Patient model."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, patient_id: int) -> Patient | None:
        return await self.db.get(Patient, patient_id)

    async def list_all(self) -> list[Patient]:
        result = await self.db.execute(select(Patient).order_by(Patient.id))
        return list(result.scalars().all())

    async def create(self, patient: Patient) -> Patient:
        self.db.add(patient)
        await self.db.flush()
        await self.db.refresh(patient)
        return patient
