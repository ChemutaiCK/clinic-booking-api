"""
Domain-level exceptions.

The service layer raises these instead of HTTPException so that business
logic stays framework-agnostic and testable in isolation. The API layer
(app/middleware/exception_handlers.py) translates each exception type into
the appropriate HTTP status code and error envelope.
"""


class AppError(Exception):
    """Base class for all handled application errors."""

    error_code: str = "APP_ERROR"
    message: str = "An application error occurred."

    def __init__(self, message: str | None = None):
        self.message = message or self.message
        super().__init__(self.message)


class NotFoundError(AppError):
    error_code = "NOT_FOUND"
    message = "The requested resource was not found."


class DoctorNotFoundError(NotFoundError):
    error_code = "DOCTOR_NOT_FOUND"
    message = "Doctor not found."


class PatientNotFoundError(NotFoundError):
    error_code = "PATIENT_NOT_FOUND"
    message = "Patient not found."


class AppointmentNotFoundError(NotFoundError):
    error_code = "APPOINTMENT_NOT_FOUND"
    message = "Appointment not found."


class ValidationError(AppError):
    error_code = "VALIDATION_ERROR"
    message = "The request failed validation."


class OutsideWorkingHoursError(ValidationError):
    error_code = "OUTSIDE_WORKING_HOURS"
    message = "The requested slot falls outside the doctor's working hours."


class InvalidSlotAlignmentError(ValidationError):
    error_code = "INVALID_SLOT_ALIGNMENT"
    message = "The requested slot must align to a 30-minute boundary starting from the doctor's work_start."


class SlotInPastError(ValidationError):
    error_code = "SLOT_IN_PAST"
    message = "The requested slot is in the past."


class SlotTooSoonError(ValidationError):
    error_code = "SLOT_TOO_SOON"
    message = "The requested slot must be booked at least one hour in advance."


class SlotNotAvailableError(AppError):
    error_code = "SLOT_NOT_AVAILABLE"
    message = "The requested slot is already booked."


class AppointmentAlreadyCancelledError(AppError):
    error_code = "APPOINTMENT_ALREADY_CANCELLED"
    message = "This appointment has already been cancelled."


class InvalidDateRangeError(ValidationError):
    error_code = "INVALID_DATE_RANGE"
    message = "The requested date range is invalid."
