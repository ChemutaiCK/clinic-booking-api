"""Shared/common Pydantic schemas."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Standard error envelope returned for all handled API errors."""

    error: str = Field(..., examples=["SLOT_NOT_AVAILABLE"])
    message: str = Field(..., examples=["The requested slot is no longer available."])
    request_id: str | None = Field(default=None, examples=["3f9a2b1e-4c2d-4a3b-9c1e-2f5b6a7c8d9e"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., examples=["ok"])
    version: str
    environment: str
