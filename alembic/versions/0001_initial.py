"""create doctors, patients, appointments tables

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-16 00:00:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doctors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("specialization", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("work_start", sa.Time(), nullable=False),
        sa.Column("work_end", sa.Time(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_doctors_email", "doctors", ["email"], unique=True)

    op.create_table(
        "patients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_patients_email", "patients", ["email"], unique=True)

    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "doctor_id",
            sa.Integer(),
            sa.ForeignKey("doctors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "patient_id",
            sa.Integer(),
            sa.ForeignKey("patients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="BOOKED"),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_appointments_doctor_id", "appointments", ["doctor_id"])
    op.create_index("ix_appointments_patient_id", "appointments", ["patient_id"])
    op.create_index("ix_appointments_slot_time", "appointments", ["slot_time"])
    op.create_index("ix_appointments_status", "appointments", ["status"])

    # The concurrency-critical constraint: only one BOOKED appointment per
    # doctor per slot_time. Cancelled appointments are excluded via the
    # partial WHERE clause, so a cancelled slot can be rebooked. See
    # app/models/appointment.py for the full rationale.
    op.create_index(
        "uq_doctor_slot_when_booked",
        "appointments",
        ["doctor_id", "slot_time"],
        unique=True,
        postgresql_where=sa.text("status = 'BOOKED'"),
        sqlite_where=sa.text("status = 'BOOKED'"),
    )


def downgrade() -> None:
    op.drop_index("uq_doctor_slot_when_booked", table_name="appointments")
    op.drop_index("ix_appointments_status", table_name="appointments")
    op.drop_index("ix_appointments_slot_time", table_name="appointments")
    op.drop_index("ix_appointments_patient_id", table_name="appointments")
    op.drop_index("ix_appointments_doctor_id", table_name="appointments")
    op.drop_table("appointments")

    op.drop_index("ix_patients_email", table_name="patients")
    op.drop_table("patients")

    op.drop_index("ix_doctors_email", table_name="doctors")
    op.drop_table("doctors")
