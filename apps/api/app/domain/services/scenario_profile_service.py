"""ScenarioProfileService — P6-A25.

Turns a free-form natural-language description of tonight's service (e.g.
"we're hosting an event today, expecting large turnover") into an ad-hoc
scenario_profile dict shaped like the 4 hardcoded presets
(domain/scenarios.py's ScenarioDefinition) -- label/service_window/
operational_focus -- so it slots into the existing planning pipeline without
any node needing to know it isn't one of the 4 literal preset ids.

The 4 presets are NOT replaced by this -- they stay as one-click shortcuts
(explicit product decision, see CLAUDE.md P6-A25). This is an alternative
intake path alongside them, not instead of them.

Never raises -- falls back to a generic profile built directly from the
input text if the LLM call fails or returns an incomplete/malformed shape,
mirroring ScenarioRecommender's never-raise + deterministic-fallback pattern.
The fallback always fills every key the pipeline needs, since
complaint_service/inventory_service/reservation_service read
scenario_profile["label"]/["service_window"]/["operational_focus"] via
direct dict-key access (not .get()) once scenario_profile is truthy.
"""

import re
from typing import Optional

import structlog

from app.infrastructure.llm.base import BaseLLMProvider

log = structlog.get_logger()

_SERVICE_WINDOW_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")
_DEFAULT_SERVICE_WINDOW = "18:00-22:00"
_MAX_INPUT_LEN = 500


class ScenarioProfileService:
    """Derives an ad-hoc scenario profile from free-form text.

    Instantiate once per request. derive_profile() never raises.
    """

    def __init__(self, llm: BaseLLMProvider) -> None:
        self.llm = llm

    # ── public ───────────────────────────────────────────────────────────────

    async def derive_profile(self, text: str) -> dict:
        """Return {id, label, description, service_window, operational_focus, cuisine}."""
        text = (text or "").strip()[:_MAX_INPUT_LEN]
        if not text:
            return self._fallback(text)
        try:
            return await self._derive(text)
        except Exception as exc:
            log.warning("scenario_profile_service_error", error=str(exc))
            return self._fallback(text)

    # ── internal ─────────────────────────────────────────────────────────────

    async def _derive(self, text: str) -> dict:
        prompt = f"""
A restaurant owner just described tonight's service in their own words:

"{text}"

Turn this into a short operational profile for the planning system. Respond
with a JSON object containing:
- "label": a short 2-4 word name for this service (e.g. "Private Event Service")
- "service_window": start-end time in 24h HH:MM-HH:MM format (e.g. "18:00-23:00") --
  infer a sensible window from the description; default to dinner hours if unclear
- "operational_focus": one sentence describing what the kitchen/floor should
  prioritize tonight, grounded in what the owner actually said
"""
        result = await self.llm.complete_json(
            prompt=prompt,
            system_prompt=(
                "You convert a restaurant owner's free-form description of tonight's "
                "service into a structured operational profile for a planning system."
            ),
        )

        if not isinstance(result, dict):
            return self._fallback(text)

        label = str(result.get("label") or "").strip()
        service_window = str(result.get("service_window") or "").strip()
        operational_focus = str(result.get("operational_focus") or "").strip()

        if not label or not operational_focus or not _SERVICE_WINDOW_RE.match(service_window):
            return self._fallback(text, label=label, operational_focus=operational_focus)

        return self._build(label=label, service_window=service_window, operational_focus=operational_focus)

    def _fallback(self, text: str, label: str = "", operational_focus: str = "") -> dict:
        return self._build(
            label=label or "Custom Service",
            service_window=_DEFAULT_SERVICE_WINDOW,
            operational_focus=operational_focus or (
                f"General service execution based on: {text}" if text else
                "General service execution -- no specific description provided."
            ),
        )

    def _build(self, label: str, service_window: str, operational_focus: str) -> dict:
        return {
            "id": "custom",
            "label": label,
            "description": operational_focus,
            "service_window": service_window,
            "operational_focus": operational_focus,
            "cuisine": None,
        }
