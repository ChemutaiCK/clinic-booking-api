"""
Application entrypoint.

Creates and configures the FastAPI app: middleware, exception handlers,
routers, CORS, structured logging, and a branded ("Fresh Meadow" themed)
Swagger UI at /docs.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config.settings import get_settings
from app.core.logging import configure_logging, get_logger
from app.middleware.exception_handlers import register_exception_handlers
from app.middleware.logging_middleware import AccessLogMiddleware
from app.middleware.request_context import RequestIDMiddleware

settings = get_settings()

configure_logging()
logger = get_logger("app.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting %s v%s in %s mode",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )
    yield
    logger.info("Shutting down %s", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "A clinic appointment booking API for Savannah Informatics. "
            "Patients can view a doctor's available slots, book, cancel, and reschedule "
            "appointments. Booking is atomic and safe under concurrent load."
        ),
        docs_url=None,  # replaced with a themed docs route below
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # --- Middleware (order matters: outermost added last executes first) ---
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIDMiddleware)

    register_exception_handlers(app)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    # Mounted at the bare root so paths match the assessment's literal spec
    # (e.g. POST /appointments, GET /doctors/{id}/availability).
    app.include_router(api_router)

    @app.get("/docs", include_in_schema=False)
    async def themed_swagger_ui():
        return get_swagger_ui_html(
            openapi_url=app.openapi_url,
            title=f"{settings.APP_NAME} - Swagger UI",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
            swagger_css_url="/static/swagger_theme.css",
        )

    return app


app = create_app()
