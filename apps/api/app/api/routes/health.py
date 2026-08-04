from fastapi import APIRouter

from app.api.schemas.common import DependenciesHealthResponse
from app.api.schemas.health import HealthResponse
from app.core.constants import SERVICE_NAME
from app.core.settings import get_settings
from app.infrastructure.observability.dependency_health import (
    check_swiggy_circuits,
    get_dependency_statuses,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        environment=settings.app_env,
    )


@router.get("/health/dependencies", response_model=DependenciesHealthResponse)
def dependencies_health_check() -> DependenciesHealthResponse:
    settings = get_settings()
    dependencies = get_dependency_statuses(settings)
    overall_ok = all(dep.ok for dep in dependencies)

    return DependenciesHealthResponse(
        service=SERVICE_NAME,
        overall_ok=overall_ok,
        dependencies=dependencies,
    )


@router.get("/health/circuits", summary="Swiggy MCP circuit breaker states")
async def circuits_health() -> dict:
    """Return current open/closed state for each Swiggy MCP endpoint."""
    return {"circuits": await check_swiggy_circuits()}