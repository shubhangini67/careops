"""
PDF report generator for CareOps AI planning runs.

Produces a one-page manager summary: critic verdict, dimension scores,
action items, and per-agent recommendation highlights.
"""

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
_AMBER   = colors.HexColor("#D97706")   # amber-600
_BLACK   = colors.HexColor("#0A0F1C")   # near-black background
_DARK    = colors.HexColor("#1E293B")   # slate-800
_MID     = colors.HexColor("#64748B")   # slate-500
_LIGHT   = colors.HexColor("#F8FAFC")   # slate-50
_GREEN   = colors.HexColor("#059669")   # emerald-600
_RED     = colors.HexColor("#DC2626")   # red-600
_YELLOW  = colors.HexColor("#D97706")   # amber-600 (revision)

_VERDICT_COLOUR = {
    "approved": _GREEN,
    "revision": _YELLOW,
    "rejected": _RED,
}

PAGE_W, PAGE_H = A4
MARGIN = 16 * mm


# ── Style helpers ─────────────────────────────────────────────────────────────

def _style(name, **kwargs) -> ParagraphStyle:
    base = {
        "fontName": "Helvetica",
        "fontSize": 10,
        "leading": 14,
        "textColor": _DARK,
        "spaceAfter": 0,
        "spaceBefore": 0,
    }
    base.update(kwargs)
    return ParagraphStyle(name, **base)


_S_TITLE     = _style("title",     fontName="Helvetica-Bold", fontSize=18, textColor=_BLACK, leading=22)
_S_SUBTITLE  = _style("subtitle",  fontName="Helvetica",      fontSize=10, textColor=_MID,   leading=13)
_S_SECTION   = _style("section",   fontName="Helvetica-Bold", fontSize=11, textColor=_BLACK, leading=14, spaceBefore=4)
_S_BODY      = _style("body",      fontSize=9,  leading=13, textColor=_DARK)
_S_SMALL     = _style("small",     fontSize=8,  leading=11, textColor=_MID)
_S_VERDICT   = _style("verdict",   fontName="Helvetica-Bold", fontSize=22, leading=26)
_S_LABEL     = _style("label",     fontName="Helvetica-Bold", fontSize=7,  textColor=_MID,   leading=10)
_S_BULLET    = _style("bullet",    fontSize=9,  leading=13, textColor=_DARK, leftIndent=10, bulletIndent=0)


# ── Main generator ────────────────────────────────────────────────────────────

def generate_run_pdf(run: dict) -> bytes:
    """
    Generate a one-page PDF manager summary for a planning run.

    Parameters
    ----------
    run : dict
        Full planning run detail dict as returned by RunService.to_detail().

    Returns
    -------
    bytes
        Raw PDF bytes, ready to stream as application/pdf.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=MARGIN,
        title=f"CareOps AI — Planning Report #{run.get('id', '?')}",
        author="CareOps AI",
    )

    story = []
    _build_header(story, run)
    _build_verdict(story, run)
    _build_dimension_scores(story, run)
    _build_action_items(story, run)
    _build_recommendations(story, run)
    _build_footer(story, run)

    doc.build(story)
    return buf.getvalue()


# ── Section builders ──────────────────────────────────────────────────────────

def _build_header(story: list, run: dict) -> None:
    scenario_label = (run.get("scenario") or "").replace("_", " ").title()
    target_date    = run.get("target_date") or "—"
    generated_at   = _fmt_dt(run.get("generated_at") or run.get("created_at"))
    run_id         = (run.get("metadata") or {}).get("run_id") or str(run.get("id", ""))

    story.append(Paragraph("CareOps AI", _S_TITLE))
    story.append(Paragraph("Planning Run — Manager Summary", _S_SUBTITLE))
    story.append(Spacer(1, 3 * mm))

    meta_data = [
        ["Scenario", "Target date", "Generated", "Run ID"],
        [scenario_label, target_date, generated_at, run_id[:8] if run_id else "—"],
    ]
    meta_table = Table(meta_data, colWidths=[(PAGE_W - 2 * MARGIN) / 4] * 4)
    meta_table.setStyle(TableStyle([
        ("FONTNAME",        (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",        (0, 0), (-1, 0),  7),
        ("TEXTCOLOR",       (0, 0), (-1, 0),  _MID),
        ("FONTNAME",        (0, 1), (-1, 1),  "Helvetica"),
        ("FONTSIZE",        (0, 1), (-1, 1),  9),
        ("TEXTCOLOR",       (0, 1), (-1, 1),  _DARK),
        ("TOPPADDING",      (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",   (0, 0), (-1, -1), 2),
        ("LEFTPADDING",     (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",    (0, 0), (-1, -1), 0),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 4 * mm))


def _build_verdict(story: list, run: dict) -> None:
    critic  = run.get("critic") or {}
    verdict = (critic.get("verdict") or "unknown").lower()
    score   = float(critic.get("score") or 0.0)
    notes   = critic.get("notes") or ""
    colour  = _VERDICT_COLOUR.get(verdict, _MID)

    verdict_style = ParagraphStyle(
        "vd", fontName="Helvetica-Bold", fontSize=22, leading=26,
        textColor=colour,
    )
    score_style = ParagraphStyle(
        "sc", fontName="Helvetica-Bold", fontSize=22, leading=26,
        textColor=_BLACK,
    )

    row = [[
        Paragraph(verdict.upper(), verdict_style),
        Paragraph(f"{score:.2f} / 1.00", score_style),
    ]]
    t = Table(row, colWidths=[(PAGE_W - 2 * MARGIN) * 0.6, (PAGE_W - 2 * MARGIN) * 0.4])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 2 * mm))

    if notes:
        story.append(Paragraph(notes, _S_BODY))

    story.append(Spacer(1, 4 * mm))


def _build_dimension_scores(story: list, run: dict) -> None:
    critic = run.get("critic") or {}
    dims   = critic.get("dimension_scores") or {}
    if not dims:
        return

    story.append(Paragraph("Dimension Scores", _S_SECTION))
    story.append(Spacer(1, 2 * mm))

    labels = ["Safety", "Feasibility", "Evidence", "Actionability", "Clarity"]
    keys   = ["safety", "feasibility", "evidence", "actionability", "clarity"]
    col_w  = (PAGE_W - 2 * MARGIN) / len(keys)

    header_row = [Paragraph(l, _S_LABEL) for l in labels]
    value_row  = [
        Paragraph(f"{float(dims.get(k, 0)):.2f}", _S_SECTION)
        for k in keys
    ]

    t = Table([header_row, value_row], colWidths=[col_w] * len(keys))
    t.setStyle(TableStyle([
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LINEBELOW",     (0, 0), (-1, 0),  0.3, colors.HexColor("#E2E8F0")),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))


def _build_action_items(story: list, run: dict) -> None:
    critic   = run.get("critic") or {}
    feedback = critic.get("actionable_feedback") or []
    if not feedback:
        return

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Action Items", _S_SECTION))
    story.append(Spacer(1, 2 * mm))

    for i, item in enumerate(feedback, 1):
        story.append(Paragraph(f"{i}.  {item}", _S_BULLET))
        story.append(Spacer(1, 1.5 * mm))

    story.append(Spacer(1, 3 * mm))


def _build_recommendations(story: list, run: dict) -> None:
    recs = run.get("recommendations") or {}
    if not recs:
        return

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Agent Recommendations", _S_SECTION))
    story.append(Spacer(1, 2 * mm))

    sections = [
        ("Demand Forecast",    recs.get("forecast",    {}), "recommendation"),
        ("Reservations",       recs.get("reservation", {}), "recommendation"),
        ("Complaints",         recs.get("complaint",   {}), "overall_summary"),
        ("Menu Intelligence",  recs.get("menu",        {}), "reasoning"),
        ("Inventory",          recs.get("inventory",   {}), "reasoning"),
    ]

    col_w = PAGE_W - 2 * MARGIN
    rows  = []
    for label, data, key in sections:
        text    = (data.get(key) or "No recommendation available.")[:300]
        priority = (data.get("priority") or "").upper()
        prio_colour = {"HIGH": _RED, "MEDIUM": _YELLOW, "LOW": _GREEN}.get(priority, _MID)
        prio_style  = ParagraphStyle(
            f"prio_{label}", fontName="Helvetica-Bold", fontSize=7,
            textColor=prio_colour, leading=9,
        )
        rows.append([
            Paragraph(label, _S_LABEL),
            Paragraph(priority, prio_style) if priority else Paragraph("", _S_SMALL),
        ])
        rows.append([
            Paragraph(text, _S_BODY),
            Paragraph("", _S_BODY),
        ])
        rows.append([Spacer(1, 1.5 * mm), Spacer(1, 1.5 * mm)])

    t = Table(rows, colWidths=[col_w * 0.88, col_w * 0.12])
    t.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))


def _build_footer(story: list, run: dict) -> None:
    meta         = run.get("metadata") or {}
    provider     = meta.get("llm_provider") or "—"
    model        = meta.get("llm_model") or "—"
    cost         = meta.get("total_cost_usd")
    tokens       = meta.get("total_tokens")
    duration_ms  = meta.get("total_duration_ms")

    parts = [f"LLM: {provider}/{model}"]
    if cost is not None:
        parts.append(f"Cost: ${float(cost):.4f}")
    if tokens is not None:
        parts.append(f"Tokens: {int(tokens):,}")
    if duration_ms is not None:
        parts.append(f"Duration: {float(duration_ms)/1000:.1f}s")

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#E2E8F0")))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("  ·  ".join(parts), _S_SMALL))


# ── Utility ───────────────────────────────────────────────────────────────────

def _fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %H:%M")
    except Exception:
        return str(value)[:16]
