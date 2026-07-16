"""Health check endpoint - used by Render/uptime monitors and load balancers."""

from fastapi import APIRouter

from app.config.settings import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])
settings = get_settings()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns 200 OK with basic service metadata. Used for uptime monitoring "
    "and deployment readiness checks.",
)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
    )
