"""Unit tests for P5-01 PDF export — report_generator."""

import io
import pytest
import pypdf
from app.infrastructure.pdf.report_generator import generate_run_pdf

MOCK_RUN = {
    "id": 42,
    "scenario": "friday_rush",
    "target_date": "2026-06-06",
    "status": "ready",
    "generated_at": "2026-06-03T10:00:00+00:00",
    "created_at": "2026-06-03T10:01:00+00:00",
    "critic_verdict": "approved",
    "critic_score": 0.92,
    "critic": {
        "verdict": "approved",
        "score": 0.92,
        "notes": "The plan appropriately addresses high occupancy and critical inventory shortages.",
        "dimension_scores": {
            "safety": 1.0,
            "feasibility": 0.95,
            "evidence": 0.90,
            "actionability": 0.90,
            "clarity": 0.90,
        },
        "actionable_feedback": [
            "Prioritise critical shortage restocking before service opens.",
            "Monitor staffing levels during peak hours.",
            "Review garlic bread inventory before Friday service.",
        ],
        "revision_reasons": [],
    },
    "recommendations": {
        "forecast": {
            "recommendation": "Increase staffing by 15% and prep 25% more for top items.",
            "priority": "high",
        },
        "reservation": {
            "recommendation": "Monitor and adjust seating assignments as needed.",
            "priority": "medium",
        },
        "complaint": {
            "overall_summary": "Main issues are stockouts and slow prep — address via inventory and kitchen workflow.",
            "priority": "high",
        },
        "menu": {
            "reasoning": "Focus on popular burger items; deprioritise pasta under inventory pressure.",
            "priority": "medium",
        },
        "inventory": {
            "reasoning": "Multiple critical shortages require immediate restocking.",
            "priority": "high",
        },
    },
    "metadata": {
        "run_id": "abc12345",
        "llm_provider": "groq",
        "llm_model": "llama-3.3-70b-versatile",
        "total_cost_usd": 0.0038,
        "total_tokens": 5800,
        "total_duration_ms": 8500,
    },
    "rag_context": {},
    "final_response": {},
}


def _extract_text(pdf_bytes: bytes) -> str:
    """Extract all text from a PDF using pypdf."""
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return " ".join(page.extract_text() or "" for page in reader.pages)


def test_generate_run_pdf_returns_bytes():
    result = generate_run_pdf(MOCK_RUN)
    assert isinstance(result, bytes)
    assert len(result) > 1000


def test_pdf_starts_with_pdf_magic_bytes():
    result = generate_run_pdf(MOCK_RUN)
    assert result[:4] == b"%PDF"


def test_pdf_is_single_page():
    result = generate_run_pdf(MOCK_RUN)
    reader = pypdf.PdfReader(io.BytesIO(result))
    assert len(reader.pages) == 1


def test_pdf_contains_verdict():
    text = _extract_text(generate_run_pdf(MOCK_RUN))
    assert "APPROVED" in text.upper()


def test_pdf_contains_critic_score():
    text = _extract_text(generate_run_pdf(MOCK_RUN))
    assert "0.92" in text


def test_pdf_contains_action_items():
    text = _extract_text(generate_run_pdf(MOCK_RUN))
    assert "Prioritise" in text or "restocking" in text.lower()


def test_pdf_contains_all_agent_sections():
    text = _extract_text(generate_run_pdf(MOCK_RUN))
    for section in ["Forecast", "Reservation", "Complaint", "Menu", "Inventory"]:
        assert section in text, f"Missing agent section: {section}"


def test_pdf_contains_llm_metadata():
    text = _extract_text(generate_run_pdf(MOCK_RUN))
    assert "groq" in text.lower()


def test_pdf_contains_dimension_scores():
    text = _extract_text(generate_run_pdf(MOCK_RUN))
    assert "Safety" in text
    assert "Feasibility" in text


def test_pdf_handles_missing_optional_fields():
    minimal = {
        "id": 1,
        "scenario": "weekday_lunch",
        "target_date": None,
        "status": "ready",
        "generated_at": None,
        "created_at": None,
        "critic": {
            "verdict": "revision",
            "score": 0.5,
            "notes": "",
            "dimension_scores": {},
            "actionable_feedback": [],
        },
        "recommendations": {},
        "metadata": {},
        "rag_context": {},
        "final_response": {},
    }
    result = generate_run_pdf(minimal)
    assert result[:4] == b"%PDF"


def test_pdf_rejected_verdict_generates_without_error():
    run = {**MOCK_RUN, "critic": {**MOCK_RUN["critic"], "verdict": "rejected", "score": 0.1}}
    result = generate_run_pdf(run)
    text = _extract_text(result)
    assert "REJECTED" in text.upper()
