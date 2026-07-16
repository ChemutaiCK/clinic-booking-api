"""Patient service: application logic for patient management."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PatientNotFoundError
from app.models.patient import Patient
from app.repositories.patient_repository import PatientRepository


class PatientService:
    def __init__(self, db: AsyncSession, patient_repo: PatientRepository):
        self.db = db
        self.patient_repo = patient_repo

    async def create_patient(self, patient: Patient) -> Patient:
        try:
            created = await self.patient_repo.create(patient)
            await self.db.commit()
            return created
        except Exception:
            await self.db.rollback()
            raise

    async def get_patient(self, patient_id: int) -> Patient:
        patient = await self.patient_repo.get_by_id(patient_id)
        if patient is None:
            raise PatientNotFoundError()
        return patient

    async def list_patients(self) -> list[Patient]:
        return await self.patient_repo.list_all()
