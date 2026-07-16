"""Pydantic schemas for Appointment resources and availability."""

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.appointment import AppointmentStatus


class AppointmentCreate(BaseModel):
    """Payload for booking a new appointment."""

    doctor_id: int = Field(..., gt=0, examples=[1])
    patient_id: int = Field(..., gt=0, examples=[1])
    slot_time: datetime = Field(
        ...,
        description="Start of the 30-minute slot, as an ISO-8601 datetime. "
        "Naive datetimes are assumed to be UTC.",
        examples=["2026-07-20T09:00:00Z"],
    )

    @field_validator("slot_time")
    @classmethod
    def ensure_timezone_aware(cls, value: datetime) -> datetime:
        """Naive datetimes are treated as UTC to avoid ambiguous bookings."""
        if value.tzinfo is None:
            from datetime import timezone

            return value.replace(tzinfo=timezone.utc)
        return value


class AppointmentCancel(BaseModel):
    """Payload for cancelling an appointment."""

    cancellation_reason: str = Field(
        ..., min_length=1, max_length=1000, examples=["Patient requested cancellation."]
    )


class AppointmentReschedule(BaseModel):
    """Payload for rescheduling an appointment to a new slot."""

    new_slot_time: datetime = Field(
        ...,
        description="Start of the new 30-minute slot. Naive datetimes are assumed to be UTC.",
        examples=["2026-07-21T10:30:00Z"],
    )

    @field_validator("new_slot_time")
    @classmethod
    def ensure_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            from datetime import timezone

            return value.replace(tzinfo=timezone.utc)
        return value


class AppointmentRead(BaseModel):
    """Appointment representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    patient_id: int
    slot_time: datetime
    status: AppointmentStatus
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime


class AvailabilityQuery(BaseModel):
    """Query parameters for the availability endpoint."""

    target_date: date = Field(..., examples=["2026-07-20"])


class AvailabilityResponse(BaseModel):
    """Available slots for a doctor on a given date."""

    doctor_id: int
    date: date
    work_start: time
    work_end: time
    slot_duration_minutes: int
    available_slots: list[datetime]
