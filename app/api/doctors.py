"""Doctor endpoints: creation, listing, and availability lookup."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.services import (
    get_appointment_service,
    get_doctor_service,
)
from app.models.doctor import Doctor
from app.schemas.appointment import AvailabilityResponse
from app.schemas.doctor import DoctorCreate, DoctorRead
from app.services.appointment_service import AppointmentService
from app.services.doctor_service import DoctorService

router = APIRouter(prefix="/doctors", tags=["Doctors"])


@router.post(
    "",
    response_model=DoctorRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor",
    description="Registers a new doctor with their specialization and daily working hours.",
)
async def create_doctor(
    payload: DoctorCreate,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> DoctorRead:
    doctor = Doctor(**payload.model_dump())
    created = await service.create_doctor(doctor)
    return DoctorRead.model_validate(created)


@router.get(
    "",
    response_model=list[DoctorRead],
    summary="List doctors",
    description="Returns all registered doctors.",
)
async def list_doctors(
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> list[DoctorRead]:
    doctors = await service.list_doctors()
    return [DoctorRead.model_validate(d) for d in doctors]


@router.get(
    "/{doctor_id}",
    response_model=DoctorRead,
    summary="Get a doctor",
    description="Returns a single doctor by ID. 404 if not found.",
)
async def get_doctor(
    doctor_id: int,
    service: Annotated[DoctorService, Depends(get_doctor_service)],
) -> DoctorRead:
    doctor = await service.get_doctor(doctor_id)
    return DoctorRead.model_validate(doctor)


@router.get(
    "/{doctor_id}/availability",
    response_model=AvailabilityResponse,
    summary="Get a doctor's available slots for a date",
    description=(
        "Returns every available 30-minute slot for the given doctor on the given date. "
        "Slots that are already booked, in the past, or within the minimum booking lead "
        "time (1 hour) are excluded. `date` is interpreted as a UTC calendar date."
    ),
)
async def get_doctor_availability(
    doctor_id: int,
    target_date: Annotated[date, Query(alias="date", description="Date in YYYY-MM-DD format.")],
    doctor_service: Annotated[DoctorService, Depends(get_doctor_service)],
    appointment_service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> AvailabilityResponse:
    doctor = await doctor_service.get_doctor(doctor_id)
    slots = await appointment_service.get_availability(doctor_id, target_date)
    return AvailabilityResponse(
        doctor_id=doctor_id,
        date=target_date,
        work_start=doctor.work_start,
        work_end=doctor.work_end,
        slot_duration_minutes=30,
        available_slots=slots,
    )
