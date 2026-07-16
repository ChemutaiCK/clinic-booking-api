"""
Seed script: populates the database with 5 doctors and a few sample
patients, matching the assessment scenario ("a small clinic with 5
doctors"). Safe to run multiple times - it skips creation if data already
exists.

Usage:
    python -m scripts.seed
"""

import asyncio
from datetime import time

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.database.session import AsyncSessionLocal
from app.models.doctor import Doctor
from app.models.patient import Patient

configure_logging()
logger = get_logger("app.seed")

DOCTORS = [
    dict(
        full_name="Dr. Amina Hassan",
        specialization="General Practice",
        email="amina.hassan@clinic.example",
        work_start=time(8, 0),
        work_end=time(16, 0),
    ),
    dict(
        full_name="Dr. Brian Kiptoo",
        specialization="Pediatrics",
        email="brian.kiptoo@clinic.example",
        work_start=time(9, 0),
        work_end=time(17, 0),
    ),
    dict(
        full_name="Dr. Grace Wanjiru",
        specialization="Dermatology",
        email="grace.wanjiru@clinic.example",
        work_start=time(10, 0),
        work_end=time(18, 0),
    ),
    dict(
        full_name="Dr. Samuel Otieno",
        specialization="Cardiology",
        email="samuel.otieno@clinic.example",
        work_start=time(8, 30),
        work_end=time(15, 30),
    ),
    dict(
        full_name="Dr. Fatima Njoroge",
        specialization="Orthopedics",
        email="fatima.njoroge@clinic.example",
        work_start=time(9, 30),
        work_end=time(17, 30),
    ),
]

PATIENTS = [
    dict(full_name="John Mwangi", email="john.mwangi@example.com"),
    dict(full_name="Mary Achieng", email="mary.achieng@example.com"),
    dict(full_name="Peter Kamau", email="peter.kamau@example.com"),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        existing = (await session.execute(select(Doctor.id))).scalars().first()
        if existing is not None:
            logger.info("Doctors already exist - skipping doctor seed.")
        else:
            for data in DOCTORS:
                session.add(Doctor(**data))
            logger.info("Seeded %d doctors.", len(DOCTORS))

        existing_patient = (await session.execute(select(Patient.id))).scalars().first()
        if existing_patient is not None:
            logger.info("Patients already exist - skipping patient seed.")
        else:
            for data in PATIENTS:
                session.add(Patient(**data))
            logger.info("Seeded %d patients.", len(PATIENTS))

        await session.commit()
    logger.info("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
