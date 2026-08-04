"""Unit tests for ScenarioProfileService (P6-A25).

All LLM calls are mocked -- no live network/API key needed.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.services.scenario_profile_service import ScenarioProfileService


def _service(llm_result=None, side_effect=None) -> ScenarioProfileService:
    llm = MagicMock()
    if side_effect is not None:
        llm.complete_json = AsyncMock(side_effect=side_effect)
    else:
        llm.complete_json = AsyncMock(return_value=llm_result)
    return ScenarioProfileService(llm)


@pytest.mark.asyncio
async def test_valid_llm_response_builds_full_profile():
    service = _service(llm_result={
        "label": "Private Event Service",
        "service_window": "18:00-23:00",
        "operational_focus": "Prioritize large-party turnover and pre-batched prep.",
    })
    profile = await service.derive_profile("we're hosting an event today, expecting large turnover")

    assert profile["id"] == "custom"
    assert profile["label"] == "Private Event Service"
    assert profile["service_window"] == "18:00-23:00"
    assert "turnover" in profile["operational_focus"]
    # every key the pipeline's direct dict-key access relies on must be present
    for key in ("id", "label", "description", "service_window", "operational_focus", "cuisine"):
        assert key in profile


@pytest.mark.asyncio
async def test_missing_label_falls_back_to_generic_profile():
    service = _service(llm_result={
        "service_window": "18:00-23:00",
        "operational_focus": "Some focus.",
    })
    profile = await service.derive_profile("some text")

    assert profile["label"] == "Custom Service"
    assert profile["service_window"] == "18:00-22:00"  # fallback default, not the LLM's window


@pytest.mark.asyncio
async def test_malformed_service_window_triggers_fallback():
    service = _service(llm_result={
        "label": "Event Night",
        "service_window": "not a time range",
        "operational_focus": "Some focus.",
    })
    profile = await service.derive_profile("some text")

    assert profile["service_window"] == "18:00-22:00"


@pytest.mark.asyncio
async def test_llm_returns_non_dict_falls_back():
    service = _service(llm_result="not a dict")
    profile = await service.derive_profile("some text")

    assert profile["label"] == "Custom Service"
    assert profile["service_window"] == "18:00-22:00"


@pytest.mark.asyncio
async def test_llm_exception_returns_fallback_not_raise():
    service = _service(side_effect=RuntimeError("LLM down"))
    profile = await service.derive_profile("we're expecting a big private party tonight")

    assert profile["label"] == "Custom Service"
    assert "big private party" in profile["operational_focus"]


@pytest.mark.asyncio
async def test_empty_text_returns_generic_fallback_without_calling_llm():
    llm = MagicMock()
    llm.complete_json = AsyncMock()
    service = ScenarioProfileService(llm)

    profile = await service.derive_profile("   ")

    llm.complete_json.assert_not_called()
    assert profile["label"] == "Custom Service"
    assert profile["service_window"] == "18:00-22:00"


@pytest.mark.asyncio
async def test_input_text_is_truncated_before_use():
    service = _service(side_effect=RuntimeError("force fallback"))
    long_text = "x" * 1000
    profile = await service.derive_profile(long_text)

    # fallback operational_focus embeds the (truncated) text -- must not blow up or embed 1000 chars
    assert len(profile["operational_focus"]) < 600
