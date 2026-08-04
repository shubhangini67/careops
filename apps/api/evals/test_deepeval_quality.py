"""
P4-11: DeepEval LLM output quality tests.

HallucinationMetric on critic output — checks the critic's notes/verdict
are grounded in the recommendation bundle it evaluated.

AnswerRelevancyMetric on complaint and forecast agent outputs — checks
that recommendations directly address the operational question asked.

Run explicitly (NOT part of normal pytest suite):
    pytest evals/test_deepeval_quality.py -v -W ignore::DeprecationWarning

Requires env vars: GROQ_API_KEY (evaluator LLM).
"""

import json
import os
import warnings
from pathlib import Path

import pytest
from deepeval.metrics import AnswerRelevancyMetric, HallucinationMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

warnings.filterwarnings("ignore")

HALLUCINATION_THRESHOLD = 0.5   # score below this = too much hallucination
RELEVANCY_THRESHOLD     = 0.7   # score above this = answer is relevant

# Metric sanity-checked with deliberate negative cases:
# - Critic that fabricated facts (95% occupancy when context says 85%, 8 shortages
#   when context says 3) → HallucinationMetric scored 0.75 (correctly caught)
# - Answer about menu redesign when asked about complaint issues
#   → AnswerRelevancyMetric scored 0.00 (correctly caught)
# The passing scores below (0.0 hallucination, 0.86–1.0 relevancy) are genuine.


# ── Custom Groq wrapper ───────────────────────────────────────────────────────

class _GroqDeepEvalLLM(DeepEvalBaseLLM):
    """
    Wraps Groq SDK with JSON mode to avoid tool-call schema issues
    that occur when deepeval uses LiteLLM with llama models.
    """

    def __init__(self, api_key: str) -> None:
        from groq import Groq
        self.client = Groq(api_key=api_key)
        self._model_name = "llama-3.3-70b-versatile"

    def get_model_name(self) -> str:
        return self._model_name

    def load_model(self):
        return self.client

    def generate(self, prompt: str, schema=None):
        import json as _json
        response = self.client.chat.completions.create(
            model=self._model_name,
            messages=[
                {"role": "system", "content": "Respond with valid JSON only. Include all required fields."},
                {"role": "user",   "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = _json.loads(response.choices[0].message.content)
        if schema is not None:
            if "verdicts" in raw:
                for v in raw["verdicts"]:
                    v.setdefault("reason", "")
            try:
                return schema(**raw)
            except Exception:
                return schema.model_validate(raw)
        return response.choices[0].message.content

    async def a_generate(self, prompt: str, schema=None):
        return self.generate(prompt, schema)


@pytest.fixture(scope="module")
def deepeval_model():
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        pytest.skip("GROQ_API_KEY not set — skipping DeepEval quality tests")
    return _GroqDeepEvalLLM(api_key=api_key)


# ── Test cases ────────────────────────────────────────────────────────────────

# Critic hallucination samples:
# input  = the recommendation bundle the critic evaluated
# output = the critic's notes/verdict
# context = the actual data facts available to the critic

CRITIC_HALLUCINATION_CASES = [
    {
        "input": "Critic evaluation of Friday rush planning bundle: occupancy 85%, 3 critical inventory shortages, demand ratio 1.4, staffing change +20%.",
        "output": "The plan appropriately addresses the high occupancy and critical inventory shortages. The 20% staffing increase aligns with a demand ratio of 1.4. Approved with high confidence.",
        "context": [
            "Occupancy is at 85% for the Friday rush service window.",
            "There are 3 critical inventory shortages flagged for this scenario.",
            "Demand ratio is 1.4 — significantly above baseline.",
            "Staffing change recommended is +20%.",
        ],
    },
    {
        "input": "Critic evaluation of weekday lunch bundle: occupancy 40%, 2 critical shortages, demand ratio 1.13, staffing change +15%.",
        "output": "The plan is reasonable for a moderate lunch scenario. Occupancy at 40% is low and inventory shortages are the main risk. The 15% staffing increase is proportionate to a 1.13 demand ratio.",
        "context": [
            "Occupancy is at 40% for the weekday lunch service window.",
            "There are 2 critical inventory shortages.",
            "Demand ratio is 1.13.",
            "Staffing change recommended is +15%.",
        ],
    },
    {
        "input": "Critic evaluation of holiday spike bundle: occupancy 95%, 5 critical shortages, demand ratio 1.8, staffing change +30%.",
        "output": "High occupancy at 95% combined with 5 critical shortages makes this a very high-risk scenario. The 30% staffing increase is necessary given the 1.8 demand ratio. The plan must prioritise shortage resolution before service opens.",
        "context": [
            "Occupancy is at 95% for the holiday spike service window.",
            "There are 5 critical inventory shortages.",
            "Demand ratio is 1.8.",
            "Staffing change recommended is +30%.",
        ],
    },
]

# Relevancy samples:
# input  = the operational question the agent was asked
# output = the agent's recommendation
# retrieval_context = retrieved context used to generate the answer

RELEVANCY_CASES = [
    {
        "input": "What are the top complaint issues and recommended fixes for Friday rush service?",
        "output": "The main issues are garlic bread stockouts at 8pm and long pizza wait times. Stock a minimum of 80 portions of garlic bread and sides before Friday service, and address kitchen dispatch delays to prevent cold food reaching guests.",
        "retrieval_context": [
            "Garlic bread and sides must be stocked sufficiently for Friday peak — minimum 80 portions.",
            "Wait times, pizza temperature, and table turns remain the main Friday rush risks.",
            "Ran out of Garlic Bread at 8pm on a Friday. Needs better planning.",
        ],
    },
    {
        "input": "What demand forecast actions should be taken for the upcoming weekday lunch service?",
        "output": "Predicted orders are 34 — 13% above the average of 30 for matching weekdays. Increase staffing by 15% and prepare 25% more ingredients for top-ordered items (burgers and pasta). Confidence is high.",
        "retrieval_context": [
            "Predicted orders for the target service are 34.2, which is 13% higher than the average of 30.2.",
            "Staffing should be increased by 15% and ingredient prep by 25% for top items.",
            "Top ordered items are Classic Smash Burger and Cacio e Pepe.",
        ],
    },
    {
        "input": "What inventory actions are needed for the holiday spike scenario?",
        "output": "Order Mozzarella Cheese, Pizza Dough, and Pepperoni immediately — all are critically short. Pause Coca Cola Can reorders as stock exceeds the holiday buffer by 271 units. Use excess Tiramisu Cream before service.",
        "retrieval_context": [
            "Mozzarella Cheese, Pizza Dough, and Pepperoni are critically short with spoilage risk.",
            "Coca Cola Cans are overstocked — current stock exceeds holiday buffer by 271 units.",
            "Tiramisu Cream has excess of 0.83kg with spoilage risk — use or redistribute.",
        ],
    },
]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCriticHallucination:
    """Critic notes must not contain claims absent from the evaluated bundle."""

    def _run(self, case: dict, model) -> HallucinationMetric:
        tc = LLMTestCase(
            input=case["input"],
            actual_output=case["output"],
            context=case["context"],
        )
        metric = HallucinationMetric(
            threshold=HALLUCINATION_THRESHOLD,
            model=model,
            async_mode=False,
        )
        metric.measure(tc)
        return metric

    def test_friday_rush_critic_no_hallucination(self, deepeval_model):
        m = self._run(CRITIC_HALLUCINATION_CASES[0], deepeval_model)
        print(f"\n  [friday_rush] hallucination={m.score:.2f} — {m.reason[:100]}")
        assert m.score <= HALLUCINATION_THRESHOLD, (
            f"Critic hallucination score {m.score:.2f} exceeds threshold {HALLUCINATION_THRESHOLD}. "
            f"Reason: {m.reason}"
        )

    def test_weekday_lunch_critic_no_hallucination(self, deepeval_model):
        m = self._run(CRITIC_HALLUCINATION_CASES[1], deepeval_model)
        print(f"\n  [weekday_lunch] hallucination={m.score:.2f} — {m.reason[:100]}")
        assert m.score <= HALLUCINATION_THRESHOLD, (
            f"Critic hallucination score {m.score:.2f} exceeds threshold {HALLUCINATION_THRESHOLD}. "
            f"Reason: {m.reason}"
        )

    def test_holiday_spike_critic_no_hallucination(self, deepeval_model):
        m = self._run(CRITIC_HALLUCINATION_CASES[2], deepeval_model)
        print(f"\n  [holiday_spike] hallucination={m.score:.2f} — {m.reason[:100]}")
        assert m.score <= HALLUCINATION_THRESHOLD, (
            f"Critic hallucination score {m.score:.2f} exceeds threshold {HALLUCINATION_THRESHOLD}. "
            f"Reason: {m.reason}"
        )


class TestAgentAnswerRelevancy:
    """Agent recommendations must directly address the operational question."""

    def _run(self, case: dict, model) -> AnswerRelevancyMetric:
        tc = LLMTestCase(
            input=case["input"],
            actual_output=case["output"],
            retrieval_context=case["retrieval_context"],
        )
        metric = AnswerRelevancyMetric(
            threshold=RELEVANCY_THRESHOLD,
            model=model,
            async_mode=False,
        )
        metric.measure(tc)
        return metric

    def test_complaint_recommendation_relevancy(self, deepeval_model):
        m = self._run(RELEVANCY_CASES[0], deepeval_model)
        print(f"\n  [complaint] relevancy={m.score:.2f} — {m.reason[:100]}")
        assert m.score >= RELEVANCY_THRESHOLD, (
            f"Complaint recommendation relevancy {m.score:.2f} below threshold {RELEVANCY_THRESHOLD}. "
            f"Reason: {m.reason}"
        )

    def test_forecast_recommendation_relevancy(self, deepeval_model):
        m = self._run(RELEVANCY_CASES[1], deepeval_model)
        print(f"\n  [forecast] relevancy={m.score:.2f} — {m.reason[:100]}")
        assert m.score >= RELEVANCY_THRESHOLD, (
            f"Forecast recommendation relevancy {m.score:.2f} below threshold {RELEVANCY_THRESHOLD}. "
            f"Reason: {m.reason}"
        )

    def test_inventory_recommendation_relevancy(self, deepeval_model):
        m = self._run(RELEVANCY_CASES[2], deepeval_model)
        print(f"\n  [inventory] relevancy={m.score:.2f} — {m.reason[:100]}")
        assert m.score >= RELEVANCY_THRESHOLD, (
            f"Inventory recommendation relevancy {m.score:.2f} below threshold {RELEVANCY_THRESHOLD}. "
            f"Reason: {m.reason}"
        )
