import structlog

from app.core.settings import Settings, get_settings
from app.infrastructure.llm.base import BaseLLMProvider


ProviderClass = type[BaseLLMProvider]


def _load_provider_class(provider_name: str) -> ProviderClass:
    if provider_name == "gemini":
        from app.infrastructure.llm.gemini import GeminiProvider

        return GeminiProvider
    if provider_name == "groq":
        from app.infrastructure.llm.groq import GroqProvider

        return GroqProvider
    if provider_name == "comet":
        from app.infrastructure.llm.comet import CometProvider

        return CometProvider
    raise KeyError(provider_name)


class FallbackLLMProvider(BaseLLMProvider):
    """Delegates calls to the primary provider, then retries on the fallback."""

    def __init__(
        self,
        primary: BaseLLMProvider,
        fallback: BaseLLMProvider | None = None,
    ) -> None:
        super().__init__()
        self.primary = primary
        self.fallback = fallback
        self.provider_name = primary.provider_name
        self.fallback_provider_name = fallback.provider_name if fallback else None
        self.model = primary.model
        self.last_provider_used: str | None = None
        self.last_fallback_used = False

    @property
    def provider_metadata(self) -> dict:
        return {
            "llm_provider": self.provider_name,
            "llm_model": self.model,
            "llm_fallback_provider": self.fallback_provider_name or "",
        }

    async def complete(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> str:
        return await self._call_with_fallback("complete", prompt, system_prompt, temperature)

    async def complete_json(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> dict:
        return await self._call_with_fallback("complete_json", prompt, system_prompt, temperature)

    async def _call_with_fallback(
        self,
        method_name: str,
        prompt: str,
        system_prompt: str | None,
        temperature: float | None = None,
    ):
        log = structlog.get_logger()
        try:
            result = await getattr(self.primary, method_name)(
                prompt, system_prompt=system_prompt, temperature=temperature,
            )
            self.last_provider_used = self.primary.provider_name
            self.last_fallback_used = False
            return result
        except Exception as exc:
            if self.fallback is None:
                self.last_provider_used = self.primary.provider_name
                self.last_fallback_used = False
                raise

            log.warning(
                "llm_primary_failed_retrying_fallback",
                primary_provider=self.primary.provider_name,
                fallback_provider=self.fallback.provider_name,
                method=method_name,
                error=str(exc),
            )
            result = await getattr(self.fallback, method_name)(
                prompt, system_prompt=system_prompt, temperature=temperature,
            )
            self.last_provider_used = self.fallback.provider_name
            self.last_fallback_used = True
            return result

    def drain_usage(self, node: str | None = None) -> list[dict]:
        records = []
        records.extend(self.primary.drain_usage(node=node))
        if self.fallback is not None:
            records.extend(self.fallback.drain_usage(node=node))
        return records


def create_llm_provider(
    settings: Settings | None = None,
    provider_classes: dict[str, ProviderClass] | None = None,
) -> FallbackLLMProvider:
    settings = settings or get_settings()
    primary_name = settings.llm_provider.strip().lower()
    supported_providers = set(provider_classes or {"gemini": None, "groq": None, "comet": None})

    if primary_name not in supported_providers:
        supported = ", ".join(sorted(supported_providers))
        raise ValueError(f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. Supported providers: {supported}.")

    fallback_name = "groq" if primary_name == "gemini" else "gemini"
    primary_class = provider_classes[primary_name] if provider_classes else _load_provider_class(primary_name)
    primary = primary_class()
    fallback = None

    if fallback_name in supported_providers:
        try:
            fallback_class = provider_classes[fallback_name] if provider_classes else _load_provider_class(fallback_name)
            fallback = fallback_class()
        except Exception as exc:
            structlog.get_logger().warning(
                "llm_fallback_unavailable",
                primary_provider=primary_name,
                fallback_provider=fallback_name,
                error=str(exc),
            )

    return FallbackLLMProvider(primary=primary, fallback=fallback)


def create_tiered_llm_providers(
    settings: Settings | None = None,
) -> dict[str, FallbackLLMProvider]:
    """
    Build a tier-keyed dict of FallbackLLMProviders backed by CometAPI.

    Fallback chain: strong → balanced → fast (each tier falls back to the one below).
    "default" is an untiered CometProvider for nodes with no tier assignment.
    """
    from app.infrastructure.llm.comet import CometProvider

    settings = settings or get_settings()
    fast_model     = settings.cometapi_model_fast
    balanced_model = settings.cometapi_model_balanced
    strong_model   = settings.cometapi_model_strong

    return {
        "fast":     FallbackLLMProvider(CometProvider(model=fast_model)),
        "balanced": FallbackLLMProvider(CometProvider(model=balanced_model), CometProvider(model=fast_model)),
        "strong":   FallbackLLMProvider(CometProvider(model=strong_model),   CometProvider(model=balanced_model)),
        "default":  FallbackLLMProvider(CometProvider()),
    }
