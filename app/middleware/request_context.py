"""
Request ID propagation.

Every incoming request is assigned a UUID (or the value of an inbound
`X-Request-ID` header, if the caller supplied one - useful for tracing a
request across services). The ID is stored in a ContextVar so the logging
formatters can attach it to every log line emitted while handling that
request, and it is also echoed back in the `X-Request-ID` response header
and in error response bodies.
"""

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

_request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_ctx_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attaches a unique request ID to every request/response cycle."""

    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get(self.header_name)
        request_id = incoming_id or str(uuid.uuid4())
        token = _request_id_ctx_var.set(request_id)
        try:
            request.state.request_id = request_id
            response = await call_next(request)
        finally:
            _request_id_ctx_var.reset(token)
        response.headers[self.header_name] = request_id
        return response
