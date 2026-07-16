# Clinic Booking API

A backend service for a small clinic (5 doctors) to let patients view available appointment
slots, book them, cancel them, and reschedule them — without ever double-booking a doctor,
even under concurrent requests.

Built for the Savannah Informatics backend take-home assessment.

**Theme:** "Fresh Meadow" — `#4CB04F` / `#EBF9EE` / `#377D39` / `#F4FCF6` / `#464646`,
applied to the Swagger UI at `/docs`.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [System Design](#system-design)
3. [Architecture](#architecture)
4. [Folder Structure](#folder-structure)
5. [Database Schema](#database-schema)
6. [Concurrency Strategy](#concurrency-strategy)
7. [Timezone Strategy](#timezone-strategy)
8. [Authentication Assumptions](#authentication-assumptions)
9. [API Endpoints](#api-endpoints)
10. [Design Decisions & Trade-offs](#design-decisions--trade-offs)
11. [Why FastAPI](#why-fastapi)
12. [Why PostgreSQL](#why-postgresql)
13. [Running Locally](#running-locally)
14. [Docker](#docker)
15. [Testing](#testing)
16. [Deployment](#deployment)
17. [CI/CD](#cicd)
18. [Security](#security)
19. [Observability](#observability)
20. [Future Improvements](#future-improvements)
21. [AI Reflection](#ai-reflection)

---

## Project Overview

The scenario: a clinic with 5 doctors, each working fixed daily hours in 30-minute slots.
Patients need to see what's free for a doctor on a given day, book a slot, and cancel or
reschedule later. Once booked, nobody else can take that slot.

The one requirement that shapes almost every other decision in this project is the
non-negotiable one: **a slot must never be double-booked, even if two booking requests
arrive at the same instant.** Everything from the schema design to the transaction
boundaries in the service layer exists to guarantee that.

---

## System Design

### Core entities

- **Doctor** — a clinician with a specialization and fixed daily working hours
  (`work_start`, `work_end`).
- **Patient** — a person who books appointments.
- **Appointment** — a link between a doctor, a patient, and a 30-minute `slot_time`, with a
  `status` (`BOOKED` / `CANCELLED`) and, for cancellations, a required reason.

### What counts as a "slot"?

I modeled slots as a **fixed grid**, not a flexible/arbitrary-start booking system. Each
doctor's day is divided into 30-minute increments starting exactly at `work_start`
(e.g. a doctor working 09:00–17:00 has slots at 09:00, 09:30, 10:00, ... 16:30). A booking
request must land exactly on one of those grid lines.

**Why a fixed grid over flexible slots:** it's simpler to reason about, trivially prevents
overlapping bookings (every slot is either the exact same slot as another or doesn't
overlap it at all — there's no partial-overlap case to handle), and matches how the
scenario describes the clinic actually operating ("works in 30-minute slots"). The
trade-off is inflexibility: this model can't represent a doctor who wants to offer a single
45-minute consultation. If that need arose, the grid would need to become
duration-aware, which is a bigger schema change (appointments would need their own
duration, and availability generation would need interval-tree logic instead of simple grid
enumeration).

**Edge case this creates:** if a doctor's `work_end` isn't itself grid-aligned to
`work_start` (e.g. `work_start=09:00`, `work_end=17:15`), the last 15 minutes are simply
unbookable — there's no partial slot. This is intentional; a 15-minute appointment isn't a
valid appointment in this system.

### Components

- **Models** (`app/models/`) — SQLAlchemy ORM classes: `Doctor`, `Patient`, `Appointment`.
- **Repositories** (`app/repositories/`) — all raw database access lives here. Nothing
  above this layer writes SQL or knows about SQLAlchemy `select()` statements.
- **Services** (`app/services/`) — business rules and transaction boundaries.
  `AppointmentService` is where booking, cancellation, and rescheduling logic — and the
  concurrency-safety guarantees — actually live.
- **API layer** (`app/api/`) — thin FastAPI routers. A route handler's job is: parse the
  request (via Pydantic), call exactly one service method, return the response. No business
  logic lives here.
- **Schemas** (`app/schemas/`) — Pydantic v2 request/response models, entirely separate
  from the ORM models, so the API's public contract can evolve independently of the
  database schema.

### Scalability

At clinic scale (5 doctors, low request volume) none of this needs to scale much. But the
design doesn't paint itself into a corner:

- The repository/service split means the database can be swapped or sharded later without
  touching route handlers.
- Locking is scoped **per doctor**, not globally — booking doctor A doesn't block booking
  doctor B. This is the main lever if the clinic "wants to grow" (per the brief) to more
  doctors: throughput scales roughly linearly with doctor count, since each doctor's
  bookings serialize independently.
- If the clinic grows into "multiple locations, hundreds of doctors, thousands of
  concurrent patients," the doctor-row-lock approach would eventually need to move to
  something with less lock contention per doctor (see
  [Concurrency Strategy](#concurrency-strategy) for the specific alternative I'd reach for).

### What happens if a doctor's working hours change?

This implementation stores `work_start`/`work_end` directly on the `Doctor` row as the
single current schedule — there's no history of past schedules. Practically, this means:

- **Future availability** immediately reflects the new hours (the availability endpoint
  always reads the current `work_start`/`work_end`).
- **Existing booked appointments are untouched** — changing a doctor's hours doesn't
  retroactively invalidate a slot that was validly booked under the old hours. A booking
  that's now technically "outside working hours" under the new schedule stays booked; it
  simply isn't offered to new bookers.
- What this design does **not** handle: alerting staff that some booked appointments now
  fall outside the doctor's new hours, or letting a doctor cancel an entire day at once
  (bulk-cancel). Both are natural extensions — see
  [Future Improvements](#future-improvements).

---

## Architecture

**Layered / Clean Architecture** with the repository pattern and dependency injection:

```
Route Handler (app/api)
        │  depends on
        ▼
   Service (app/services)      ← business rules, transaction boundaries
        │  depends on
        ▼
 Repository (app/repositories)  ← raw DB access only
        │  uses
        ▼
   ORM Model (app/models)
        │
        ▼
    PostgreSQL
```

Every layer is wired together through FastAPI's `Depends()` (see
`app/dependencies/services.py`), so:

- Route handlers never import SQLAlchemy.
- Services never import FastAPI.
- Everything is independently testable — a service can be unit-tested with a fake
  repository, with zero HTTP or DB machinery involved.

---

## Folder Structure

```
app/
    api/              # FastAPI routers (doctors, patients, appointments, health)
    core/             # Cross-cutting concerns: exceptions, logging
    config/           # Pydantic-settings configuration
    database/         # Engine/session setup, declarative Base, custom column types
    models/           # SQLAlchemy ORM models
    repositories/      # Data-access layer
    services/         # Business logic layer
    schemas/          # Pydantic request/response models
    dependencies/     # FastAPI DI wiring
    middleware/       # Request ID propagation, access logging, exception handlers
    static/           # Swagger UI theme CSS
    main.py           # App factory / entrypoint
alembic/              # Database migrations
scripts/
    seed.py           # Seeds 5 doctors + sample patients
tests/                # pytest suite (async, SQLite-backed)
docker/
    Dockerfile
    entrypoint.sh
.github/workflows/
    ci.yml            # Lint → test → deploy pipeline
docker-compose.yml
render.yaml           # Render Blueprint (Infrastructure as Code)
Makefile
```

---

## Database Schema

```
doctors                          appointments                        patients
---------------------------      ---------------------------------   -----------------------
id              PK        <----- doctor_id        FK                 id              PK
full_name                        patient_id        FK  --------->    full_name
specialization                   id                PK                email          UNIQUE
email          UNIQUE            slot_time         (UTC)              created_at
work_start     (time)            status  (BOOKED / CANCELLED)         updated_at
work_end       (time)            cancellation_reason
created_at                       created_at
updated_at                       updated_at

  UNIQUE INDEX ON appointments(doctor_id, slot_time)
  WHERE status = 'BOOKED'          <- the double-booking guarantee
```

- Foreign keys: `appointments.doctor_id → doctors.id`, `appointments.patient_id →
  patients.id`, both `ON DELETE CASCADE`.
- Unique constraints: `doctors.email`, `patients.email`, and the **partial** unique index
  on `appointments(doctor_id, slot_time)` — see below.
- Indexes: on all foreign keys, on `slot_time` and `status` (both filtered on
  constantly), to keep availability and history queries fast.
- All timestamps are UTC (see [Timezone Strategy](#timezone-strategy)).

### Why a *partial* unique index, not a plain one

A plain `UNIQUE(doctor_id, slot_time)` constraint would permanently block a slot the
moment it's ever booked — even after cancellation, since the cancelled row would still
occupy that unique key. Making the index **partial** (`WHERE status = 'BOOKED'`) means only
active bookings compete for uniqueness; a cancelled appointment stops counting, and the
slot becomes bookable again immediately.

---

## Concurrency Strategy

This is the requirement the assessment weights most heavily, so it gets the most detailed
treatment.

### The failure mode being prevented

The naive implementation is:

```python
# DON'T DO THIS
existing = query_slot(doctor_id, slot_time)
if existing:
    raise SlotTaken()
create_appointment(doctor_id, slot_time)
```

This is a **check-then-act (TOCTOU) race**. Two requests can both run the `existing` check
before either has committed its `create_appointment`. Both see "free," both insert. Result:
two `BOOKED` rows for the same doctor and slot — exactly the "both patients got a
confirmation" incident this kind of bug produces in production.

### The fix: two independent, redundant layers

**Layer 1 — row lock (`SELECT ... FOR UPDATE`) on the doctor.**
`book_appointment` and `reschedule_appointment` both start by acquiring a row lock on the
`Doctor` row via `doctor_repo.get_by_id_locked()`. On PostgreSQL, this means: if two
requests for the *same doctor* arrive concurrently, the second one blocks at the lock
acquisition step until the first transaction commits or rolls back. So the "check
availability → insert" sequence is effectively serialized per doctor — request #2's
availability check only runs *after* request #1 has already committed, so it correctly
sees the slot as taken and returns `409`.

I lock the **doctor** row rather than a row representing the slot itself, because the slot
doesn't necessarily have a row to lock yet (nothing exists at that `slot_time` until
someone books it). The doctor row always exists, so it's a natural, cheap serialization
point.

**Layer 2 — the database-level partial unique index** described above. This is the *real*
source of truth, not just a backup: even if the application-level lock were ever bypassed —
a bug that removes it, a second service touching the same database directly, a future
engineer refactoring without reading this doc — the database physically cannot store two
`BOOKED` rows for the same `(doctor_id, slot_time)`. The insert raises `IntegrityError`,
which the service catches and translates into a clean `409 SLOT_NOT_AVAILABLE` response
rather than a raw database error leaking to the client.

I deliberately kept both layers rather than relying on just the constraint. The constraint
alone would work correctly (an `IntegrityError` on the losing request is a perfectly valid
way to prevent double-booking) — but without the row lock, *every* concurrent booking
attempt for a busy doctor would race down to the database and rely on catching exceptions
as the normal control flow for conflicts, which is noisier (harder to reason about, noisier
logs, exception-driven control flow as the primary mechanism rather than a safety net) than
serializing them upfront. With the lock in place, `IntegrityError` should be rare in
practice; when it does eventually fire, that's the signal something bypassed the normal
path, and it's still handled cleanly.

### Reschedule atomicity

Rescheduling is implemented as updating the **same appointment row's** `slot_time` in
place inside one transaction, rather than "cancel the old row, create a new one." This
matters for the exact question the assessment raises: *if the new slot is taken by the
time the reschedule is processed, does the patient lose their original slot?*

**No.** Because it's a single-row update inside one transaction: either the whole thing
succeeds (row moves to the new `slot_time`, old `slot_time` is implicitly freed since
nothing points at it anymore) or the validation/constraint check fails and the **entire
transaction rolls back**, leaving the appointment exactly where it started. There's no
window where the old slot is freed but the new one isn't secured — see
`test_reschedule_to_taken_slot_rolls_back` in the test suite, which asserts this directly:
it books two appointments, tries to reschedule one onto the other's slot, confirms the
`409`, and then re-fetches the first appointment to confirm it's still at its original
`slot_time`.

### Trade-offs of this approach

- **Lock scope:** locking the doctor row serializes *all* booking/reschedule attempts for
  that doctor, even for different, non-conflicting slots. At clinic scale this is a
  non-issue (a doctor isn't fielding dozens of simultaneous booking requests per second).
  At much larger scale, this would become a bottleneck, and I'd reach for a PostgreSQL
  advisory lock keyed on `(doctor_id, slot_time)` instead of `FOR UPDATE` on the doctor
  row — that serializes only conflicting requests, not every request for a doctor.
- **Why I didn't build that from the start:** advisory locks add real complexity (manual
  lock/unlock bookkeeping, more subtle failure modes if a connection drops mid-lock) for a
  problem this system doesn't have yet. The partial unique index is correct regardless of
  which locking strategy sits in front of it, so upgrading the lock layer later is a
  self-contained change.

---

## Timezone Strategy

**All appointment timestamps are stored and processed in UTC.** Specifically:

- `Appointment.slot_time`, `created_at`, and `updated_at` use a custom `UTCDateTime`
  SQLAlchemy type (`app/database/types.py`) that normalizes every value to naive-UTC on
  the way into the database and re-attaches UTC tzinfo on the way out. I built this instead
  of relying on the plain `DateTime(timezone=True)` type because SQLite (used in the test
  suite) doesn't actually preserve timezone-aware datetimes the way PostgreSQL does —
  without this normalization layer, the exact same code would behave subtly differently
  between tests and production, which is precisely the kind of bug that's invisible until
  it isn't.
- The API accepts ISO-8601 datetimes for `slot_time` / `new_slot_time`. A naive datetime
  (no offset) is treated as UTC rather than rejected — a pragmatic default for an API
  that's implicitly clinic-local in this iteration (see below).
- `Doctor.work_start` / `work_end`, by contrast, are stored as **naive `time`** values —
  deliberately *not* datetimes. They represent a recurring daily schedule ("9 to 5, every
  day"), not a specific instant, so they shouldn't carry a date or a timezone at all. The
  availability-generation logic combines these with a requested date to build a UTC
  datetime grid.

**What this design assumes, and doesn't yet handle:** it implicitly assumes the clinic
operates in a single timezone and that `work_start`/`work_end` are quoted in that
timezone (currently treated as equal to UTC for simplicity, since the assessment doesn't
specify a location). A real deployment would need a `timezone` field on `Doctor` (or on a
`Clinic` entity if the system grows to multiple locations), and the availability
calculation would convert `work_start`/`work_end` from clinic-local time into UTC before
building the slot grid, rather than assuming they're already UTC. I noted this as a
documented assumption per the assessment's own rule ("when requirements are ambiguous, make
a decision and note it").

---

## Authentication Assumptions

**No authentication is implemented in this submission.** This is a deliberate, explicit
scope decision, not an oversight — the assessment brief doesn't specify an auth model, and
bolting on a specific scheme (JWT? session cookies? API keys?) without a real requirement
to design against would mean guessing at requirements that weren't asked for.

What I'd actually build for production, and why:

- **Patients** should authenticate (e.g. JWT bearer tokens) and only be able to book,
  cancel, or reschedule *their own* appointments — `patient_id` should come from the
  authenticated session, never from the request body, closing the "any caller can book on
  behalf of any patient" hole entirely.
- **Doctors/clinic staff** likely need a separate role with broader permissions (view all
  appointments for their own schedule, potentially cancel on a patient's behalf with
  audit logging).
- Doctor and patient **creation** endpoints (`POST /doctors`, `POST /patients`) are
  currently open, which is appropriate for seeding an assessment demo but would need to
  be admin-only (or removed in favor of an internal registration flow) in production.

This is called out explicitly rather than silently shipped, because "no auth" is a load-
bearing assumption that changes how seriously every other security control in this system
should be read.

---

## API Endpoints

All endpoints are documented interactively at `/docs` (themed Swagger UI) and `/redoc`.

| Method | Path | Description |
|---|---|---|
| `POST` | `/appointments` | Book a slot. Validates doctor/patient existence, working hours, grid alignment, not-in-past, ≥1hr lead time, not-already-booked. |
| `GET` | `/doctors/{id}/availability?date=YYYY-MM-DD` | Returns every free 30-minute slot for a doctor on a date. |
| `PATCH` | `/appointments/{id}/cancel` | Cancels an appointment. Requires `cancellation_reason`. 409 if already cancelled. |
| `PATCH` | `/appointments/{id}/reschedule` | Moves an appointment to a new slot, validated exactly like a fresh booking. Atomic. |
| `GET` | `/patients/{id}/appointments` | *(Bonus)* Patient's upcoming `BOOKED` appointments, soonest first. |
| `POST` | `/doctors` | Register a doctor. |
| `GET` | `/doctors` / `GET /doctors/{id}` | List / fetch doctors. |
| `POST` | `/patients` | Register a patient. |
| `GET` | `/patients` / `GET /patients/{id}` | List / fetch patients. |
| `GET` | `/appointments/{id}` | Fetch a single appointment. |
| `GET` | `/health` | Health check (used by Render and CI). |

### Example: booking a slot

```bash
curl -X POST https://<your-deployed-url>/appointments \
  -H "Content-Type: application/json" \
  -d '{
        "doctor_id": 1,
        "patient_id": 1,
        "slot_time": "2026-07-20T09:00:00Z"
      }'
```

Success → `201`:
```json
{
  "id": 1,
  "doctor_id": 1,
  "patient_id": 1,
  "slot_time": "2026-07-20T09:00:00+00:00",
  "status": "BOOKED",
  "cancellation_reason": null,
  "created_at": "2026-07-16T08:00:00+00:00",
  "updated_at": "2026-07-16T08:00:00+00:00"
}
```

Slot already taken → `409`:
```json
{
  "error": "SLOT_NOT_AVAILABLE",
  "message": "The requested slot is already booked.",
  "request_id": "3f9a2b1e-4c2d-4a3b-9c1e-2f5b6a7c8d9e"
}
```

Every error response follows this same `{error, message, request_id}` envelope, with a
matching HTTP status code (`404` not found, `409` conflict, `422` validation).

---

## Design Decisions & Trade-offs

Summarized (most are explained at length in their own sections above):

| Decision | Alternative considered | Why this one |
|---|---|---|
| Fixed 30-min slot grid | Flexible/arbitrary-duration slots | Matches the brief exactly; trivially prevents partial overlaps |
| Row lock + partial unique index (two layers) | Unique index alone | Fewer exception-driven conflicts under normal load; constraint remains the safety net |
| Reschedule = update same row | Cancel old + create new | True atomicity — no window where old slot is freed but new isn't secured |
| Custom `UTCDateTime` type | Plain `DateTime(timezone=True)` | SQLite (tests) doesn't preserve tzinfo the way PostgreSQL does; this closes that gap |
| No auth in this submission | Guess at a scheme | Not specified in the brief; guessing risks building the wrong thing |
| Doctor working hours as naive `time` | Full datetime | They're a recurring daily schedule, not a single instant |

---

## Why FastAPI

- **Async-native**, which matters directly for this project: the concurrency guarantees
  described above depend on the request handling itself being non-blocking, so a doctor's
  row lock is held for the shortest possible window.
- **Pydantic v2 integration** gives request/response validation, OpenAPI generation, and
  editor-level type checking essentially for free, which pays off directly in the
  "meaningful error messages with correct status codes" requirement.
- Auto-generated, interactive OpenAPI docs (`/docs`, `/redoc`) — useful both for the
  reviewer evaluating this submission and for real API consumers.
- Dependency injection is a first-class language feature (`Depends()`), which is what
  makes the clean layering (routers → services → repositories) straightforward to wire up
  without a separate DI framework.

## Why PostgreSQL

- **True partial unique indexes** with a `WHERE` clause — the mechanism this entire
  concurrency strategy is built on — are a first-class PostgreSQL feature.
- **`SELECT ... FOR UPDATE`** row locking with proper MVCC semantics is exactly the
  primitive the concurrency strategy needs, and PostgreSQL's behavior here is
  well-understood and battle-tested.
- It's free, open-source, and both Render (deployment target) and Docker Compose (local
  dev) support it as a first-class managed/local service, so there's no operational
  overhead in either environment.
- Healthcare data (even this simplified model) benefits from PostgreSQL's strong
  consistency guarantees and mature tooling (Alembic migrations, `pg_isready` health
  checks, etc.) over a more relaxed eventual-consistency store.

---

## Running Locally

### Prerequisites
- Python 3.12
- PostgreSQL 16 (or Docker, see below)

### Steps

```bash
# 1. Clone and enter the repo
git clone <your-repo-url>
cd clinic-booking-api

# 2. Install dependencies
make install                 # creates .venv, installs requirements, installs pre-commit hooks

# 3. Configure environment
cp .env.example .env         # edit DATABASE_URL if not using the default local Postgres

# 4. Run migrations
source .venv/bin/activate
make migrate

# 5. Seed sample data (5 doctors + 3 patients)
make seed

# 6. Run the API
make run                     # http://localhost:8000/docs
```

## Docker

The whole stack (API + PostgreSQL) runs with one command:

```bash
make docker-up               # equivalent to: docker compose up --build
```

This builds the multi-stage `docker/Dockerfile` (a slim runtime image with a non-root
user), starts PostgreSQL, waits for its health check to pass, runs Alembic migrations
automatically via `docker/entrypoint.sh`, and starts the API on `http://localhost:8000`.

```bash
make docker-down             # stop and remove containers
make docker-logs             # tail logs
```

To seed sample data into the Dockerized database:
```bash
docker compose exec api python -m scripts.seed
```

---

## Testing

```bash
make test           # run the full suite
make test-cov        # with coverage report
```

The suite runs against a temporary file-based SQLite database (created and destroyed per
test run) rather than requiring a live PostgreSQL instance — this keeps the suite fast and
dependency-free in CI, while the `UTCDateTime` type and partial unique index (both created
identically on SQLite and PostgreSQL) ensure the behavior under test matches production.

**Coverage includes every scenario called out in the assessment:**

- Successful booking
- Double booking (409)
- Cancellation
- Cancelling twice (409)
- Rescheduling (including verifying the freed original slot is rebookable)
- Reschedule onto an already-taken slot -> rollback verified (appointment stays put)
- Reschedule of a cancelled appointment (409)
- Availability generation (correct slot count, excludes booked slots)
- Invalid doctor (404)
- Invalid patient (404)
- Outside working hours (422)
- Misaligned slot / off-grid (422)
- Booking in the past (422)
- Booking within one hour of now (422) — tested deterministically via a wide-working-hours
  fixture and a "ceil to next grid slot" helper, so the test doesn't depend on what time of
  day the suite happens to run
- **Concurrent booking** — two simultaneous requests for the identical doctor/slot via
  `asyncio.gather`; asserts exactly one `201` and one `409`, then independently confirms
  via the availability endpoint that only one booking exists
- Transaction rollback (the reschedule-onto-taken-slot test doubles as this)

A note on the concurrency test specifically: SQLite has no row-level locking, so it doesn't
exercise the `SELECT ... FOR UPDATE` layer — but it does exercise the full request →
service → partial-unique-index path, which is what actually prevents the double-booking
regardless of which lock layer sits in front of it. The `FOR UPDATE` layer is a PostgreSQL
production behavior, validated manually against the Docker Compose Postgres instance.

---

## Deployment

**Public URL:** `<fill in after deploying — see below>`

Deployed on **Render**, defined as code in `render.yaml` (a Render Blueprint): a Docker
web service plus a managed PostgreSQL instance, wired together via Render's
`fromDatabase` env var injection.

To deploy your own copy:
1. Push this repo to GitHub/GitLab.
2. In the Render dashboard: **New → Blueprint**, point it at the repo. Render reads
   `render.yaml` and provisions both the web service and the database automatically.
3. Once live, copy the service's **Deploy Hook URL** (Settings → Deploy Hook) into a
   GitHub Actions secret named `RENDER_DEPLOY_HOOK_URL` — this is what the CI/CD pipeline
   calls on merge (see below).
4. Update this README's public URL above.

## CI/CD

Pipeline: `.github/workflows/ci.yml`, three jobs — **Lint → Test → Deploy**.

- **Triggers:** every pull request into `main` runs lint + test. A push to `main`
  (i.e. a merge) additionally runs the `deploy` job.
- **Lint job:** `ruff`, `black --check`, `isort --check-only`.
- **Test job:** spins up a real PostgreSQL 16 service container (not SQLite) and runs the
  full `pytest` suite against it, matching production more closely than the local
  SQLite-based default.
- **Deploy job:** only runs on a push to `main` (i.e. after a PR merge), and only after
  lint and test both pass. It triggers Render's deploy hook via a simple authenticated
  `curl` POST — Render then pulls the latest `main`, rebuilds the Docker image, and runs
  the entrypoint's `alembic upgrade head` before starting the new instance.
- **Branch that triggers deployment:** `main`, via the `push` event (which is exactly what
  a merge produces) — pull request events never trigger deployment, only lint+test.

---

## Security

- **Input validation** end-to-end via Pydantic v2 (types, formats, custom validators
  like working-hours ordering and timezone coercion).
- **No hardcoded secrets** — all configuration (`DATABASE_URL`, CORS origins, log level)
  comes from environment variables via `pydantic-settings`; `.env` is git-ignored;
  `.env.example` documents the shape without real values.
- **SQL injection protection** — 100% of queries go through SQLAlchemy's Core/ORM query
  builder with bound parameters; there is no raw string-interpolated SQL anywhere in the
  codebase.
- **CORS** — configurable via `CORS_ALLOWED_ORIGINS`; defaults to permissive for local
  dev/demo purposes, should be locked down to the real frontend origin(s) in production.
- **No PII leakage** — response schemas are explicit allow-lists (Pydantic response
  models), not raw ORM object dumps, so a field can never leak into a response just
  because it exists on the database row.
- **Centralized error handling** (`app/middleware/exception_handlers.py`) — every error
  path returns a safe, generic message; raw exception strings, stack traces, and database
  error internals never reach the client. Unexpected exceptions are caught by a catch-all
  handler and logged server-side with full detail, while the client only sees a generic
  `500`.
- **No authentication** — see [Authentication Assumptions](#authentication-assumptions)
  for why this is an explicit, documented scope decision rather than an omission.

## Observability

- **Structured JSON logging** in production (`app/core/logging.py`) — every log line
  includes a timestamp, level, logger name, message, and `request_id`. Human-readable
  formatting is used automatically in local development (`LOG_JSON=false`).
- **Request IDs** — every request gets a UUID (or reuses an inbound `X-Request-ID` header
  for cross-service tracing), propagated through a `ContextVar` so every log line emitted
  while handling that request carries it, echoed back in the response header, and included
  in every error response body — so a user-reported error can be traced to its exact log
  lines.
- **Access logging** — method, path, status code, and latency for every request.
- **Startup/shutdown logging** — via FastAPI's `lifespan` context.
- **Health endpoint** (`GET /health`) — used by Render's health checks, the Docker
  `HEALTHCHECK` directive, and CI.
- **What I'd instrument next for real production traffic:** error tracking (Sentry) for
  automatic alerting on the catch-all exception handler firing; latency percentile metrics
  (p50/p95/p99) per endpoint, since "average latency" hides exactly the kind of tail
  latency that lock contention on a busy doctor would produce; and distributed tracing if
  this ever splits into more than one service.

## Future Improvements

Roughly in priority order if this went to production:

1. **Authentication & authorization** (see above) — the single biggest gap.
2. **Doctor-scoped advisory locks** instead of `FOR UPDATE` on the doctor row, to reduce
   lock contention if a doctor's booking volume grows significantly.
3. **Clinic/doctor timezone field** — remove the current UTC-equals-clinic-local
   assumption.
4. **Bulk operations** — a doctor cancelling an entire day at once (cancel all `BOOKED`
   appointments for a doctor on a date, each with a shared reason).
5. **Working-hours history** — track changes to a doctor's schedule over time rather than
   overwriting in place, so past appointments can be understood in the context of the
   hours that were in effect when they were booked.
6. **Rate limiting** on the booking endpoint, to blunt both abuse and accidental
   thundering-herd retries from a flaky frontend.
7. **Pagination** on list endpoints (`GET /doctors`, `GET /patients`,
   `GET /patients/{id}/appointments`) — fine at 5 doctors, not fine at 5,000.
8. **Idempotency keys** on `POST /appointments`, so a client retrying a timed-out request
   doesn't risk a duplicate booking attempt being interpreted as a fresh one (today, a
   retry is actually already safe thanks to the concurrency guarantees — it would just
   receive a `409` on the slot it already booked — but an idempotency key would let it
   receive the *original* `201` back instead, which is a nicer client experience).

---

## AI Reflection

Answering the four questions from Section 4 of the assessment honestly, based on the work
actually done in this repository:

**1. What did you use AI for across the four sections?**
Brainstorming the initial project structure and confirming the layering conventions
(repository/service split, DI wiring) against common FastAPI production patterns;
reviewing the concurrency approach before committing to it; drafting and then tightening
this README's structure; and generating the initial test scaffolding, which I then
rewrote in places (see Q3) once I traced through how it would actually behave.

**2. Give one example where an AI suggestion improved your work.**
The first draft of the "1-hour lead time" test booked a slot at a hardcoded wall-clock-
relative offset from `datetime.now()`, which is inherently flaky — depending on what time
the suite runs, the same offset can land inside or outside the doctor's working hours, or
even in the past. The fix was to inject `now` explicitly wherever business rules depend on
it (the service methods already took `now` as an explicit parameter, which made this
straightforward) and to build a dedicated wide-working-hours doctor fixture plus a "ceil to
the next grid boundary" helper, so the test is guaranteed to always land inside the
"too soon" window regardless of the actual time of day. That's the version in the current
test suite.

**3. Give one example where AI output was wrong or incomplete and how you caught it.**
An early version of the `Appointment.slot_time` column used a plain
`DateTime(timezone=True)`, which is correct for PostgreSQL but silently degrades to naive
datetimes on SQLite. This was only caught by tracing through what would happen when the
test suite (SQLite-backed) serialized a fetched `Appointment` back to JSON and compared it
against an expected timezone-aware datetime in a test assertion — the comparison would have
raised `TypeError: can't compare offset-naive and offset-aware datetimes`, which would have
either failed confusingly or, worse, been "fixed" by loosening the test rather than fixing
the actual cross-database inconsistency. The real fix was the custom `UTCDateTime` type
decorator in `app/database/types.py`, which normalizes timezone handling identically on
both SQLite and PostgreSQL, so the test suite is actually validating production behavior
rather than SQLite-specific behavior.

**4. Name two decisions you made without AI. Why did you trust your own judgment there?**
- **Locking the doctor row rather than the slot** to serialize concurrent bookings. This
  follows directly from a basic fact about `SELECT ... FOR UPDATE` — it requires a row
  that already exists, and a not-yet-booked slot has no row — so there wasn't really a
  decision to defer; it's a direct consequence of the constraint being designed around,
  and it was straightforward to be confident in the reasoning chain end-to-end.
- **Making the reschedule operation update the existing appointment row in place**, rather
  than cancel-and-recreate. This was trusted because the failure mode it closes is
  directly traceable: the assessment's own reviewer-facing question ("what if the new slot
  is taken by the time reschedule is processed — does the patient lose their original
  slot?") describes exactly the bug a two-step cancel-then-create approach would have, and
  a single-row update inside one transaction structurally cannot exhibit that bug — there's
  no intermediate state where the old slot is gone and the new one isn't secured. This was
  a case where reasoning through the specific failure mode by hand was more reliable than
  asking what a "good" implementation looks like in the abstract.
