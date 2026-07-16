"""Appointment endpoints: booking, cancellation, and reschedule."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies.services import get_appointment_service
from app.schemas.appointment import (
    AppointmentCancel,
    AppointmentCreate,
    AppointmentRead,
    AppointmentReschedule,
)
from app.schemas.common import ErrorResponse
from app.services.appointment_service import AppointmentService

router = APIRouter(prefix="/appointments", tags=["Appointments"])

_COMMON_ERROR_RESPONSES = {
    404: {"model": ErrorResponse, "description": "Doctor, patient, or appointment not found."},
    409: {"model": ErrorResponse, "description": "The slot is already booked, or already cancelled."},
    422: {
        "model": ErrorResponse,
        "description": "Validation error (bad payload, past slot, outside hours, etc.).",
    },
}


@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment",
    description=(
        "Books a 30-minute slot for a patient with a doctor. Validates that the doctor "
        "and patient exist, the slot falls within the doctor's working hours, is aligned "
        "to a 30-minute grid, is not in the past, is at least one hour from now, and is "
        "not already booked. Booking is atomic and safe under concurrent requests - see "
        "the README's Concurrency Strategy section."
    ),
    responses=_COMMON_ERROR_RESPONSES,
)
async def book_appointment(
    payload: AppointmentCreate,
    service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> AppointmentRead:
    appointment = await service.book_appointment(
        doctor_id=payload.doctor_id,
        patient_id=payload.patient_id,
        slot_time=payload.slot_time,
    )
    return AppointmentRead.model_validate(appointment)


@router.patch(
    "/{appointment_id}/cancel",
    response_model=AppointmentRead,
    summary="Cancel an appointment",
    description=(
        "Cancels an appointment, requiring a cancellation reason. The freed slot becomes "
        "bookable again. Returns 409 if the appointment is already cancelled."
    ),
    responses=_COMMON_ERROR_RESPONSES,
)
async def cancel_appointment(
    appointment_id: int,
    payload: AppointmentCancel,
    service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> AppointmentRead:
    appointment = await service.cancel_appointment(
        appointment_id=appointment_id,
        cancellation_reason=payload.cancellation_reason,
    )
    return AppointmentRead.model_validate(appointment)


@router.patch(
    "/{appointment_id}/reschedule",
    response_model=AppointmentRead,
    summary="Reschedule an appointment",
    description=(
        "Moves an appointment to a new slot. The new slot is validated exactly as a fresh "
        "booking would be. The move happens atomically - if validation fails or the new "
        "slot is taken, the appointment remains at its original slot. Returns 409 if the "
        "appointment is already cancelled or the new slot is taken."
    ),
    responses=_COMMON_ERROR_RESPONSES,
)
async def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> AppointmentRead:
    appointment = await service.reschedule_appointment(
        appointment_id=appointment_id,
        new_slot_time=payload.new_slot_time,
    )
    return AppointmentRead.model_validate(appointment)


@router.get(
    "/{appointment_id}",
    response_model=AppointmentRead,
    summary="Get an appointment",
    description="Returns a single appointment by ID. 404 if not found.",
)
async def get_appointment(
    appointment_id: int,
    service: Annotated[AppointmentService, Depends(get_appointment_service)],
) -> AppointmentRead:
    appointment = await service.get_appointment(appointment_id)
    return AppointmentRead.model_validate(appointment)
