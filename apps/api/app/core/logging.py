import logging
import structlog


def configure_logging(debug: bool = False) -> None:
    """Configure structlog with JSON output and contextvars support."""

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if debug:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Silence noisy uvicorn/httpx loggers so they don't double-print
    for name in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
