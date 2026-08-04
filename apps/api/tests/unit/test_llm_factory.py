import pytest

from app.infrastructure.llm.base import BaseLLMProvider
from app.infrastructure.llm.factory import FallbackLLMProvider, create_llm_provider


class FakeProvider(BaseLLMProvider):
    def __init__(self, provider_name: str, model: str = "fake-model", fail: bool = False) -> None:
        super().__init__()
        self.provider_name = provider_name
        self.model = model
        self.fail = fail
        self.calls = 0

    async def complete(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.provider_name} failed")
        self.record_usage(self.model, prompt_tokens=10, completion_tokens=5)
        return f"{self.provider_name}: {prompt}"

    async def complete_json(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> dict:
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.provider_name} failed")
        self.record_usage(self.model, prompt_tokens=12, completion_tokens=6)
        return {"provider": self.provider_name, "prompt": prompt}


class FakeSettings:
    def __init__(self, llm_provider: str) -> None:
        self.llm_provider = llm_provider


def test_create_llm_provider_selects_configured_primary_provider():
    provider = create_llm_provider(
        settings=FakeSettings("groq"),
        provider_classes={
            "gemini": lambda: FakeProvider("gemini"),
            "groq": lambda: FakeProvider("groq", model="groq-model"),
        },
    )

    assert provider.provider_name == "groq"
    assert provider.model == "groq-model"
    assert provider.fallback_provider_name == "gemini"
    assert provider.provider_metadata == {
        "llm_provider": "groq",
        "llm_model": "groq-model",
        "llm_fallback_provider": "gemini",
    }


@pytest.mark.asyncio
async def test_fallback_provider_retries_complete_when_primary_fails():
    primary = FakeProvider("gemini", fail=True)
    fallback = FakeProvider("groq")
    provider = FallbackLLMProvider(primary=primary, fallback=fallback)

    response = await provider.complete("hello")

    assert response == "groq: hello"
    assert primary.calls == 1
    assert fallback.calls == 1
    assert provider.last_provider_used == "groq"
    assert provider.last_fallback_used is True
    assert provider.drain_usage()[0]["provider"] == "groq"


@pytest.mark.asyncio
async def test_fallback_provider_retries_complete_json_when_primary_fails():
    provider = FallbackLLMProvider(
        primary=FakeProvider("gemini", fail=True),
        fallback=FakeProvider("groq"),
    )

    response = await provider.complete_json("json please")

    assert response == {"provider": "groq", "prompt": "json please"}
    assert provider.last_provider_used == "groq"
    assert provider.last_fallback_used is True


@pytest.mark.asyncio
async def test_primary_provider_success_does_not_call_fallback():
    primary = FakeProvider("gemini")
    fallback = FakeProvider("groq")
    provider = FallbackLLMProvider(primary=primary, fallback=fallback)

    response = await provider.complete("hello")

    assert response == "gemini: hello"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert provider.last_provider_used == "gemini"
    assert provider.last_fallback_used is False
    assert provider.drain_usage()[0]["provider"] == "gemini"


def test_create_llm_provider_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        create_llm_provider(
            settings=FakeSettings("ollama"),
            provider_classes={
                "gemini": lambda: FakeProvider("gemini"),
                "groq": lambda: FakeProvider("groq"),
            },
        )
