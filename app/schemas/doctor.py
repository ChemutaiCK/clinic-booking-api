"""Pydantic schemas for Doctor resources."""

from datetime import time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class DoctorBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=150, examples=["Dr. Jane Wanjiru"])
    specialization: str = Field(..., min_length=1, max_length=150, examples=["Pediatrics"])
    email: EmailStr = Field(..., examples=["jane.wanjiru@clinic.example"])
    work_start: time = Field(..., examples=["09:00:00"])
    work_end: time = Field(..., examples=["17:00:00"])

    @model_validator(mode="after")
    def validate_working_hours(self) -> "DoctorBase":
        if self.work_end <= self.work_start:
            raise ValueError("work_end must be later than work_start")
        return self


class DoctorCreate(DoctorBase):
    """Payload for creating a doctor."""

    pass


class DoctorRead(DoctorBase):
    """Doctor representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
