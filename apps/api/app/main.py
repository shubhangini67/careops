import asyncio
import os
import sys
import time

import sentry_sdk
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.api.routes import get_api_router
from app.api.routes.replay import router as replay_router
from app.api.schemas.common import ErrorResponse
from app.core.constants import SERVICE_NAME
from app.core.exceptions import AppError
from app.core.logging import configure_logging
from app.core.settings import get_settings


# 0. Windows defaults to ProactorEventLoop, which psycopg's async mode
# cannot run under (checkpointing's AsyncPostgresSaver needs it) -- must be
# set before any event loop is created, i.e. before uvicorn starts its own.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 1. Initialize Settings
settings = get_settings()

# 2. Configure structlog
configure_logging(debug=settings.app_debug)
log = structlog.get_logger()

# 3. Sentry — skip silently if DSN is not configured
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=1.0,
        send_default_pii=False,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    log.info("sentry_enabled", environment=settings.app_env)

# 4. Propagate LangSmith config into OS env so the langsmith SDK picks it up
if settings.langsmith_api_key:
    os.environ.setdefault("LANGSMITH_TRACING",  settings.langsmith_tracing)
    os.environ.setdefault("LANGSMITH_API_KEY",   settings.langsmith_api_key)
    os.environ.setdefault("LANGSMITH_PROJECT",   settings.langsmith_project)
    os.environ.setdefault("LANGSMITH_ENDPOINT",  settings.langsmith_endpoint)

# 4b. Propagate Langfuse config into OS env so the langfuse SDK picks it up
# (P6-A27, Kindred replay debugging). langfuse-python reads LANGFUSE_BASE_URL
# first, falling back to LANGFUSE_HOST — set both so either .env naming works.
if settings.langfuse_secret_key:
    host = settings.langfuse_base_url or settings.langfuse_host
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    if host:
        os.environ.setdefault("LANGFUSE_BASE_URL", host)
        os.environ.setdefault("LANGFUSE_HOST", host)
    if settings.kindred_agent_id:
        os.environ.setdefault("KINDRED_AGENT_ID", settings.kindred_agent_id)
    log.info("langfuse_enabled")


# 2. Create the FastAPI Instance
app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)


# 3. OpenTelemetry — HTTP-layer tracing (console exporter disabled; use OTLP in prod)
_tracer_provider = TracerProvider()
# ConsoleSpanExporter floods dev logs — re-enable by adding BatchSpanProcessor(ConsoleSpanExporter())
FastAPIInstrumentor.instrument_app(app, tracer_provider=_tracer_provider)

# 3b. CORS Middleware — set CORS_ORIGINS on Render to your Vercel URL.
_cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 4. HTTP access log middleware
@app.middleware("http")
async def http_logging_middleware(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    t0 = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - t0) * 1000, 2)
    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


# 5. Global Exception Handler
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    payload = ErrorResponse(
        error_code=exc.error_code,
        message=exc.message,
        details=exc.details,
    )
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump(mode="json"))


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    return {
        "message": f"Welcome to {SERVICE_NAME}",
        "docs": "/docs",
    }


@app.get("/debug/sentry-test", tags=["debug"], include_in_schema=settings.app_debug)
def sentry_test():
    """Raises an intentional error to verify Sentry capture is working."""
    raise RuntimeError("Sentry smoke test — intentional error from CareOps AI API")


# 6. Prometheus metrics — exposes /metrics in Prometheus text format
Instrumentator().instrument(app).expose(app)

# 7. Include Modular Routes
app.include_router(get_api_router())

# 7b. Kindred replay endpoint — bare /replay, not under /api/v1 (P6-A27):
# Kindred's Configure Replay URL convention expects the endpoint at the root.
app.include_router(replay_router)