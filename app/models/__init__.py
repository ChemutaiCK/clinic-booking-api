"""
ORM models package.

Importing every model here ensures Alembic's `target_metadata` (which
points at `Base.metadata`) sees all tables when autogenerating migrations,
even if a given model module is never imported elsewhere.
"""

from app.database.base import Base
from app.models.appointment import Appointment, AppointmentStatus
from app.models.doctor import Doctor
from app.models.patient import Patient

__all__ = ["Base", "Doctor", "Patient", "Appointment", "AppointmentStatus"]
