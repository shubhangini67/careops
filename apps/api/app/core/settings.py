from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# BaseSettings is a powerful Pydantic class that automatically 
# loads environment variables into Python objects with type validation.
class Settings(BaseSettings):
    # Field allows us to define defaults and 'aliases'. 
    # The 'alias' is the name of the variable in your .env file or OS environment.
    app_name: str = Field(default="CareOps AI API", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")

    # Database and Service URLs
    # Pydantic will ensure these are strings and provide the local fallback if not found.
    postgres_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/careops",
        alias="POSTGRES_URL",
    )
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    cometapi_key: str = Field(default="", alias="COMETAPI_KEY")
    cometapi_model_fast: str = Field(default="deepseek-v4-flash", alias="COMETAPI_MODEL_FAST")
    cometapi_model_balanced: str = Field(default="gemini-3.5-flash", alias="COMETAPI_MODEL_BALANCED")
    cometapi_model_strong: str = Field(default="claude-sonnet-4-6", alias="COMETAPI_MODEL_STRONG")
    comet_tiered: bool = Field(default=False, alias="COMET_TIERED")

    # Auth
    jwt_secret_key: str = Field(default="change-me-in-production", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(default=60 * 24 * 7, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES")

    # Comma-separated browser origins allowed to call the API (Vercel URL in production).
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ORIGINS",
    )

    # Sentry error tracking (leave blank to disable)
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")

    # Swiggy MCP (dev convenience — production uses connectors table per org)
    swiggy_access_token: str = Field(default="", alias="SWIGGY_ACCESS_TOKEN")
    swiggy_address_id: str = Field(default="", alias="SWIGGY_ADDRESS_ID")
    swiggy_dineout_restaurant_id: str = Field(default="", alias="SWIGGY_DINEOUT_RESTAURANT_ID")
    # Empty until Swiggy staging creds land -- gates book_table/checkout execution
    # (mcp-staging.swiggy.com/{server}, same shape as prod, seeded data, no real orders).
    swiggy_staging_base_url: str = Field(default="", alias="SWIGGY_STAGING_BASE_URL")

    # Twilio WhatsApp Sandbox (demo procurement-messaging flow, P6-A9)
    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_whatsapp_from: str = Field(default="", alias="TWILIO_WHATSAPP_FROM")
    twilio_whatsapp_to: str = Field(default="", alias="TWILIO_WHATSAPP_TO")

    # LangSmith tracing
    langsmith_tracing: str = Field(default="false", alias="LANGSMITH_TRACING")
    langsmith_api_key: str = Field(default="", alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="CareOps AI", alias="LANGSMITH_PROJECT")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com", alias="LANGSMITH_ENDPOINT")

    # Langfuse tracing (P6-A27, Kindred replay debugging)
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    # Langfuse's own quickstart snippet uses LANGFUSE_BASE_URL; Kindred's setup
    # prompt asks for LANGFUSE_HOST. The SDK checks both — support either name.
    langfuse_host: str = Field(default="", alias="LANGFUSE_HOST")
    langfuse_base_url: str = Field(default="", alias="LANGFUSE_BASE_URL")
    kindred_agent_id: str = Field(default="", alias="KINDRED_AGENT_ID")
    kindred_api_key: str = Field(default="", alias="KINDRED_API_KEY")

    # model_config defines global behavior for this Settings class
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

# @lru_cache (Least Recently Used cache) is a decorator that 'remembers' 
# the result of the function.
@lru_cache
def get_settings() -> Settings:
    """
    This function initializes the Settings class. 
    Because of @lru_cache, the .env file is only read and parsed once. 
    Subsequent calls to get_settings() return the exact same cached object,
    making it very efficient for dependency injection.
    """
    return Settings()
