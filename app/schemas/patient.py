"""Pydantic schemas for Patient resources."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class PatientBase(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=150, examples=["John Otieno"])
    email: EmailStr = Field(..., examples=["john.otieno@example.com"])


class PatientCreate(PatientBase):
    """Payload for creating a patient."""

    pass


class PatientRead(PatientBase):
    """Patient representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
