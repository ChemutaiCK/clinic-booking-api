"""
Tests for appointment booking, cancellation, and rescheduling business logic.

Covers every scenario called out in the assessment brief: successful
booking, double booking, cancellation, cancelling twice, rescheduling,
availability, invalid doctor, invalid patient, outside working hours,
booking in the past, booking within one hour, concurrent booking, and
transaction rollback.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import ceil_to_grid, future_slot


@pytest.mark.asyncio
async def test_successful_booking(client, seeded_doctor, seeded_patient):
    slot = future_slot(days_ahead=2, hour=9, minute=0)
    response = await client.post(
        "/appointments",
        json={
            "doctor_id": seeded_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": slot.isoformat(),
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["doctor_id"] == seeded_doctor.id
    assert body["patient_id"] == seeded_patient.id
    assert body["status"] == "BOOKED"
    assert body["cancellation_reason"] is None


@pytest.mark.asyncio
async def test_double_booking_returns_409(client, seeded_doctor, seeded_patient):
    slot = future_slot(days_ahead=2, hour=10, minute=0)
    payload = {
        "doctor_id": seeded_doctor.id,
        "patient_id": seeded_patient.id,
        "slot_time": slot.isoformat(),
    }
    first = await client.post("/appointments", json=payload)
    assert first.status_code == 201

    second = await client.post("/appointments", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "SLOT_NOT_AVAILABLE"


@pytest.mark.asyncio
async def test_cancellation(client, seeded_doctor, seeded_patient):
    slot = future_slot(days_ahead=2, hour=11, minute=0)
    booked = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    appointment_id = booked.json()["id"]

    response = await client.patch(
        f"/appointments/{appointment_id}/cancel",
        json={"cancellation_reason": "Patient is unavailable."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED"
    assert body["cancellation_reason"] == "Patient is unavailable."


@pytest.mark.asyncio
async def test_cancelling_twice_returns_409(client, seeded_doctor, seeded_patient):
    slot = future_slot(days_ahead=2, hour=12, minute=0)
    booked = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    appointment_id = booked.json()["id"]

    first_cancel = await client.patch(
        f"/appointments/{appointment_id}/cancel", json={"cancellation_reason": "Change of plans."}
    )
    assert first_cancel.status_code == 200

    second_cancel = await client.patch(
        f"/appointments/{appointment_id}/cancel", json={"cancellation_reason": "Trying again."}
    )
    assert second_cancel.status_code == 409
    assert second_cancel.json()["error"] == "APPOINTMENT_ALREADY_CANCELLED"


@pytest.mark.asyncio
async def test_rescheduling(client, seeded_doctor, seeded_patient):
    original_slot = future_slot(days_ahead=2, hour=13, minute=0)
    booked = await client.post(
        "/appointments",
        json={
            "doctor_id": seeded_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": original_slot.isoformat(),
        },
    )
    appointment_id = booked.json()["id"]

    new_slot = future_slot(days_ahead=2, hour=14, minute=0)
    response = await client.patch(
        f"/appointments/{appointment_id}/reschedule",
        json={"new_slot_time": new_slot.isoformat()},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BOOKED"
    assert datetime.fromisoformat(body["slot_time"]) == new_slot

    # The original slot must now be bookable again by someone else.
    rebook = await client.post(
        "/appointments",
        json={
            "doctor_id": seeded_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": original_slot.isoformat(),
        },
    )
    assert rebook.status_code == 201


@pytest.mark.asyncio
async def test_reschedule_cancelled_appointment_returns_409(client, seeded_doctor, seeded_patient):
    slot = future_slot(days_ahead=2, hour=15, minute=0)
    booked = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    appointment_id = booked.json()["id"]

    await client.patch(
        f"/appointments/{appointment_id}/cancel", json={"cancellation_reason": "No longer needed."}
    )

    new_slot = future_slot(days_ahead=2, hour=15, minute=30)
    response = await client.patch(
        f"/appointments/{appointment_id}/reschedule", json={"new_slot_time": new_slot.isoformat()}
    )
    assert response.status_code == 409
    assert response.json()["error"] == "APPOINTMENT_ALREADY_CANCELLED"


@pytest.mark.asyncio
async def test_reschedule_to_taken_slot_rolls_back(client, seeded_doctor, seeded_patient):
    """
    Transaction rollback: if the target slot is already taken by another
    appointment, the reschedule must fail cleanly and the original
    appointment must remain untouched at its original slot_time.
    """
    slot_a = future_slot(days_ahead=3, hour=9, minute=0)
    slot_b = future_slot(days_ahead=3, hour=9, minute=30)

    appt_1 = await client.post(
        "/appointments",
        json={
            "doctor_id": seeded_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": slot_a.isoformat(),
        },
    )
    appt_2 = await client.post(
        "/appointments",
        json={
            "doctor_id": seeded_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": slot_b.isoformat(),
        },
    )
    appt_1_id = appt_1.json()["id"]

    # Attempt to move appointment 1 onto appointment 2's slot - must fail.
    response = await client.patch(
        f"/appointments/{appt_1_id}/reschedule", json={"new_slot_time": slot_b.isoformat()}
    )
    assert response.status_code == 409
    assert response.json()["error"] == "SLOT_NOT_AVAILABLE"

    # Appointment 1 must still be exactly where it started - the rollback
    # must not have partially applied the move.
    check = await client.get(f"/appointments/{appt_1_id}")
    assert check.status_code == 200
    assert datetime.fromisoformat(check.json()["slot_time"]) == slot_a
    assert check.json()["status"] == "BOOKED"


@pytest.mark.asyncio
async def test_availability_excludes_booked_slots(client, seeded_doctor, seeded_patient):
    target_date = (datetime.now(timezone.utc) + timedelta(days=2)).date()
    booked_slot = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc).replace(
        hour=9, minute=0
    )

    booked = await client.post(
        "/appointments",
        json={
            "doctor_id": seeded_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": booked_slot.isoformat(),
        },
    )
    assert booked.status_code == 201

    response = await client.get(
        f"/doctors/{seeded_doctor.id}/availability", params={"date": target_date.isoformat()}
    )
    assert response.status_code == 200
    body = response.json()

    slot_times = {datetime.fromisoformat(s) for s in body["available_slots"]}
    assert booked_slot not in slot_times
    # Doctor works 09:00-17:00 -> 16 total 30-min slots, minus the 1 booked.
    assert len(slot_times) == 15
    # Every returned slot must actually be within working hours.
    for s in slot_times:
        assert s.time() >= seeded_doctor.work_start
        assert (s + timedelta(minutes=30)).time() <= seeded_doctor.work_end


@pytest.mark.asyncio
async def test_invalid_doctor_returns_404(client, seeded_patient):
    slot = future_slot(days_ahead=1)
    response = await client.post(
        "/appointments",
        json={"doctor_id": 999999, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "DOCTOR_NOT_FOUND"


@pytest.mark.asyncio
async def test_invalid_patient_returns_404(client, seeded_doctor):
    slot = future_slot(days_ahead=1)
    response = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": 999999, "slot_time": slot.isoformat()},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "PATIENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_outside_working_hours_returns_422(client, seeded_doctor, seeded_patient):
    # Doctor works 09:00-17:00; 07:00 is before opening.
    slot = future_slot(days_ahead=1, hour=7, minute=0)
    response = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "OUTSIDE_WORKING_HOURS"


@pytest.mark.asyncio
async def test_booking_in_the_past_returns_422(client, seeded_doctor, seeded_patient):
    slot = datetime.now(timezone.utc) - timedelta(days=1)
    response = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "SLOT_IN_PAST"


@pytest.mark.asyncio
async def test_booking_within_one_hour_returns_422(client, wide_hours_doctor, seeded_patient):
    """
    Deterministic test for the bonus rule: bookings within 1 hour of now
    must be rejected. We use a near-all-day doctor fixture so the
    working-hours rule can never interfere, and ceil "now" to the next
    30-minute grid boundary so the chosen slot is always in the future but
    always well under the 60-minute lead-time threshold, regardless of what
    time the test suite happens to run.
    """
    now = datetime.now(timezone.utc)
    slot = ceil_to_grid(now)
    if slot == now:
        slot = slot + timedelta(minutes=30)

    response = await client.post(
        "/appointments",
        json={
            "doctor_id": wide_hours_doctor.id,
            "patient_id": seeded_patient.id,
            "slot_time": slot.isoformat(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"] == "SLOT_TOO_SOON"


@pytest.mark.asyncio
async def test_misaligned_slot_returns_422(client, seeded_doctor, seeded_patient):
    slot = future_slot(days_ahead=1, hour=9, minute=15)  # not on the 30-min grid
    response = await client.post(
        "/appointments",
        json={"doctor_id": seeded_doctor.id, "patient_id": seeded_patient.id, "slot_time": slot.isoformat()},
    )
    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_SLOT_ALIGNMENT"


@pytest.mark.asyncio
async def test_concurrent_booking_only_one_succeeds(client, seeded_doctor, seeded_patient):
    """
    The critical concurrency test: fire two booking requests for the exact
    same doctor/slot at the same time. Exactly one must succeed with 201;
    the other must fail with 409 SLOT_NOT_AVAILABLE. No double-booking.
    """
    slot = future_slot(days_ahead=4, hour=9, minute=0)
    payload = {
        "doctor_id": seeded_doctor.id,
        "patient_id": seeded_patient.id,
        "slot_time": slot.isoformat(),
    }

    responses = await asyncio.gather(
        client.post("/appointments", json=payload),
        client.post("/appointments", json=payload),
        return_exceptions=False,
    )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201, 409], f"expected exactly one success and one conflict, got {statuses}"

    conflict = next(r for r in responses if r.status_code == 409)
    assert conflict.json()["error"] == "SLOT_NOT_AVAILABLE"

    # Confirm the availability endpoint agrees: exactly one BOOKED row exists.
    target_date = slot.date()
    availability = await client.get(
        f"/doctors/{seeded_doctor.id}/availability", params={"date": target_date.isoformat()}
    )
    slot_times = {datetime.fromisoformat(s) for s in availability.json()["available_slots"]}
    assert slot not in slot_times
