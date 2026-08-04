from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# MetaInfo acts as a reusable 'header' for all your responses.
class MetaInfo(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# A standard success message 
class MessageResponse(BaseModel):
    message: str
    # Automatically nests a MetaInfo object with a current timestamp
    meta: MetaInfo = Field(default_factory=MetaInfo)


# Represents the health of a single external service (like Postgres or Redis)
class DependencyStatus(BaseModel):
    name: str
    ok: bool
    detail: str
    latency_ms: float | None = None


# A complex response used for a /health check endpoint
class DependenciesHealthResponse(BaseModel):
    service: str
    overall_ok: bool
    dependencies: list[DependencyStatus]
    meta: MetaInfo = Field(default_factory=MetaInfo)


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    meta: MetaInfo = Field(default_factory=MetaInfo)