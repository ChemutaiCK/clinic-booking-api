"""Patient endpoints: creation, listing, and appointment history."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies.services import get_appointment_service, get_patient_service
from app.models.patient import Patient
from app.schemas.appointment import AppointmentRead
from app.schemas.patient import PatientCreate, PatientRead
from app.services.appointment_service import AppointmentService
from app.services.patient_service import PatientService

router = APIRouter(prefix="/patients", tags=["Patients"])


@router.post(
    "",
    response_model=PatientRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a patient",
    description="Registers a new patient.",
)
async def create_patient(
    payload: PatientCreate,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> PatientRead:
    patient = Patient(**payload.model_dump())
    created = await service.create_patient(patient)
    return PatientRead.model_validate(created)


@router.get(
    "",
    response_model=list[PatientRead],
    summary="List patients",
    description="Returns all registered patients.",
)
async def list_patients(
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> list[PatientRead]:
    patients = await service.list_patients()
    return [PatientRead.model_validate(p) for p in patients]


@router.get(
    "/{patient_id}",
    response_model=PatientRead,
    summary="Get a patient",
    description="Returns a single patient by ID. 404 if not found.",
)
async def get_patient(
    patient_id: int,
    service: Annotated[PatientService, Depends(get_patient_service)],
) -> PatientRead:
    patient = await service.get_patient(patient_id)
    return PatientRead.model_validate(patient)


@router.get(
    "/{patient_id}/appointments",
    response_model=list[AppointmentRead],
    summary="List a patient's upcoming appointments",
    description="Returns the patient's upcoming BOOKED appointments, sorted by date ascending. (Bonus endpoint.)",
)
async def get_patient_appointments(
    patient_id: int,
    appointment_service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> list[AppointmentRead]:
    appointments = await appointment_service.list_upcoming_for_patient(patient_id)
    return [AppointmentRead.model_validate(a) for a in appointments]
