from fastapi import APIRouter

from app.api.routes.action_queue import router as action_queue_router
from app.api.routes.auth import router as auth_router
from app.api.routes.business import router as business_router
from app.api.routes.chat import router as chat_router
from app.api.routes.concierge import router as concierge_router
from app.api.routes.connectors import router as connectors_router
from app.api.routes.health import router as health_router
from app.api.routes.market import router as market_router
from app.api.routes.planning import router as planning_router
from app.api.routes.restaurant_profiles import router as restaurant_profiles_router
from app.api.routes.runs import router as runs_router
from app.api.routes.settings import router as settings_router
from app.api.routes.vendors import router as vendors_router
from app.core.settings import get_settings


def get_api_router() -> APIRouter:
    settings = get_settings()
    router = APIRouter(prefix=settings.api_v1_prefix)

    router.include_router(action_queue_router)
    router.include_router(auth_router)
    router.include_router(business_router)
    router.include_router(chat_router)
    router.include_router(concierge_router)
    router.include_router(connectors_router)
    router.include_router(health_router)
    router.include_router(market_router)
    router.include_router(planning_router)
    router.include_router(restaurant_profiles_router)
    router.include_router(runs_router)
    router.include_router(settings_router)
    router.include_router(vendors_router)

    return router
