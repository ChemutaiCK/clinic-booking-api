"""Top-level API router that aggregates all resource routers."""

from fastapi import APIRouter

from app.api import appointments, doctors, health, patients

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(doctors.router)
api_router.include_router(patients.router)
api_router.include_router(appointments.router)
