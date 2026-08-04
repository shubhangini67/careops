# Scenario intake modes

CareOps AI's planning pipeline (`ops_manager_node` onward) always needs a
`scenario_profile` : a `label`/`service_window`/`operational_focus` triple
that shapes every downstream agent's prompt (demand forecast, reservations,
inventory, menu, the critic). There are three ways to get one, and all three
feed the exact same pipeline unchanged from that point on.

## Mode 1: Presets (unchanged, still the default)

Four hardcoded scenarios in `apps/api/app/domain/scenarios.py`
(`SCENARIO_DEFINITIONS`): `friday_rush`, `weekday_lunch`, `holiday_spike`,
`low_stock_weekend`. Each ships a real `label`/`service_window`/
`operational_focus`/`default_weekday`. Picking one via the tile grid in
`PlanShiftModal.tsx` sends `scenario: "friday_rush"` (etc.) with no
`custom_profile`: `ops_manager_node` resolves the profile from
`get_scenario_definition()`, exactly as it always has.

These are one-click shortcuts and are **not replaced** by Mode 2: that was
an explicit product decision, not a stepping stone to deprecating them.

## Mode 2: Natural-language intake (new)

For anything that doesn't fit a preset ("we're hosting an event today,
expecting large turnover"), the owner types free text in `PlanShiftModal.tsx`
instead of picking a tile. That text goes to
`POST /planning/scenario-from-text`, which runs it through
`ScenarioProfileService.derive_profile()` (an LLM call, same never-raise +
deterministic-fallback pattern as `ScenarioRecommender`) and returns a
`ScenarioProfilePayload`: `{id: "custom", label, service_window,
operational_focus, cuisine}`.

The frontend then sends `scenario: "custom"` + `custom_profile: {...}` on the
actual `POST /planning/run` (or `/stream`) call. `ops_manager_node` sees a
`scenario` outside the 4 presets, finds `custom_profile` present, and builds
`scenario_profile` directly from it instead of `get_scenario_definition()`.
Every other node reads `scenario_profile` the same way regardless of which
mode produced it.

**Why this is safe by construction:** `ScenarioProfileService` always emits
`label`/`service_window`/`operational_focus` (falling back to a generic
profile grounded in the raw text if the LLM call fails or returns something
malformed), because `complaint_service.py`/`inventory_service.py`/
`reservation_service.py` read those keys via direct dict access
(`scenario_profile["label"]`, not `.get()`) once `scenario_profile` is
truthy: a profile missing any of the three would `KeyError` deep in the
pipeline otherwise.

**Caching:** custom-profile runs skip the semantic cache and the plan-result
cache entirely (`apps/api/app/orchestration/graph.py`,
`apps/api/app/api/routes/planning.py`): two different free-text
descriptions would otherwise collide on the same `scenario="custom"` cache
key.

## Mode 3: Live dynamic composition ("Run for today")

`GET /planning/compose-live-scenario` backs the instant "Run for today" path.
Unlike `/planning/recommend`, which picks one of the four fixed presets,
`LiveScenarioComposer.compose()` builds a brand new profile from what is
actually true right now: real day-of-week, current time, weather, holiday
context, inventory shortage count, and area occupancy. This means it can
never produce a mismatched label, such as recommending a "weekend" preset
on a Wednesday, which is a real failure mode `ScenarioRecommender` can hit
since it only chooses among four fixed presets. The response is shaped
identically to `POST /planning/scenario-from-text`'s output
(`ScenarioProfilePayload` plus a `reason`, a `confidence` score, and the
`signals_used` list), so the frontend can pass it straight through as
`custom_profile`, exactly like Mode 2.

`useScenarioRecommendation.ts` calls this endpoint and hour-caches the
result client-side (`lib/hourCache.ts`), since the underlying signals do
not change meaningfully within a single hour and composing a fresh profile
is itself an LLM call.

## Page layout

The natural-language input, the four preset tiles, and a condensed
live-signals context strip (`TodayContextStrip`, weather and holiday,
industry trends, regulatory alerts, and the anonymised Swiggy area
occupancy signal) all live together in `PlanShiftModal.tsx`, opened from
the "Run a plan" trigger on the `/planning` page. See
`docs/ARCHITECTURE.md`'s "Information architecture history: Today and
Planning" section for how this page relates to `/dashboard`.
