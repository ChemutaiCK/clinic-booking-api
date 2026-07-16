"""
Dependency-injection composition root.

FastAPI's `Depends` mechanism is used to construct repositories and services
per-request, wired to the request-scoped DB session. Route handlers only
ever depend on service classes - they never talk to repositories or the DB
session directly - which keeps the API layer thin and testable.
"""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies.database import get_db
from app.repositories.appointment_repository import AppointmentRepository
from app.repositories.doctor_repository import DoctorRepository
from app.repositories.patient_repository import PatientRepository
from app.services.appointment_service import AppointmentService
from app.services.doctor_service import DoctorService
from app.services.patient_service import PatientService


def get_doctor_repository(db: Annotated[AsyncSession, Depends(get_db)]) -> DoctorRepository:
    return DoctorRepository(db)


def get_patient_repository(db: Annotated[AsyncSession, Depends(get_db)]) -> PatientRepository:
    return PatientRepository(db)


def get_appointment_repository(db: Annotated[AsyncSession, Depends(get_db)]) -> AppointmentRepository:
    return AppointmentRepository(db)


def get_doctor_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    doctor_repo: Annotated[DoctorRepository, Depends(get_doctor_repository)],
) -> DoctorService:
    return DoctorService(db=db, doctor_repo=doctor_repo)


def get_patient_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    patient_repo: Annotated[PatientRepository, Depends(get_patient_repository)],
) -> PatientService:
    return PatientService(db=db, patient_repo=patient_repo)


def get_appointment_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    doctor_repo: Annotated[DoctorRepository, Depends(get_doctor_repository)],
    patient_repo: Annotated[PatientRepository, Depends(get_patient_repository)],
    appointment_repo: Annotated[AppointmentRepository, Depends(get_appointment_repository)],
) -> AppointmentService:
    return AppointmentService(
        db=db,
        doctor_repo=doctor_repo,
        patient_repo=patient_repo,
        appointment_repo=appointment_repo,
    )
