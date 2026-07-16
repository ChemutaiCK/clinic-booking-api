"""
Centralized exception handling.

Every handled exception is converted into a consistent JSON error envelope
(see app.schemas.common.ErrorResponse) with an appropriate HTTP status code.
This keeps error-shape decisions out of the route handlers and guarantees
that internal error details (stack traces, DB error strings) never leak to
API consumers - only a safe, generic message does.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    AppError,
    AppointmentAlreadyCancelledError,
    NotFoundError,
    SlotNotAvailableError,
    ValidationError,
)
from app.core.logging import get_logger
from app.middleware.request_context import get_request_id

logger = get_logger("app.errors")

_STATUS_MAP: dict[type[AppError], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    SlotNotAvailableError: status.HTTP_409_CONFLICT,
    AppointmentAlreadyCancelledError: status.HTTP_409_CONFLICT,
}


def _status_for(exc: AppError) -> int:
    """Walk the exception's MRO to find the most specific mapped status code."""
    for exc_type in type(exc).__mro__:
        if exc_type in _STATUS_MAP:
            return _STATUS_MAP[exc_type]
    return status.HTTP_400_BAD_REQUEST


def _error_body(error_code: str, message: str) -> dict:
    return {
        "error": error_code,
        "message": message,
        "request_id": get_request_id(),
    }


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all exception handlers to the FastAPI app instance."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        status_code = _status_for(exc)
        if status_code >= 500:
            logger.error("Unhandled application error: %s", exc.message, exc_info=True)
        else:
            logger.info("Handled application error: %s (%s)", exc.message, exc.error_code)
        return JSONResponse(
            status_code=status_code,
            content=_error_body(exc.error_code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Flatten pydantic's nested error list into a single readable message
        # without leaking internal schema paths beyond the field name.
        first_error = exc.errors()[0] if exc.errors() else {}
        field = ".".join(str(loc) for loc in first_error.get("loc", []) if loc != "body")
        detail = first_error.get("msg", "Invalid request payload.")
        message = f"{field}: {detail}" if field else detail
        logger.info("Request validation failed: %s", message)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body("VALIDATION_ERROR", message),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        # This is the last line of defense against double-booking: even if the
        # service-layer row lock were somehow bypassed, the database's partial
        # unique constraint on (doctor_id, slot_time) will reject the insert,
        # and we translate that low-level DB error into a clean 409 response.
        logger.warning("Database integrity error (likely a race on booking): %s", str(exc.orig))
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_body(
                "SLOT_NOT_AVAILABLE",
                "The requested slot is already booked.",
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unexpected error handling request: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body("INTERNAL_SERVER_ERROR", "An unexpected error occurred."),
        )
