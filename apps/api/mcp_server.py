"""
CareOps AI MCP Server — P4-12, expanded P6-A13

Exposes five tools to Claude Desktop (or any MCP client):
  • run_planning_scenario — triggers the multi-agent planning pipeline
  • get_run_history       — fetches recent planning runs with critic verdicts
  • get_market_brief      — live market snapshot (pricing, positioning, deals, occupancy)
  • get_action_queue      — lists pending (or other-status) Action Queue items
  • approve_action        — approves an action by ID; for a WhatsApp vendor order,
                            this is the same step that actually sends the message

Runs as a stdio MCP server. Authenticates against the CareOps AI API
on first tool call and reuses the JWT for the session.

Usage (stdio):
    python mcp_server.py

Configure in Claude Desktop via claude_desktop_config.json — see
docs/mcp_claude_desktop_config.json for the exact snippet.
"""

import asyncio
import json
import os
import sys
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

# ── Config ───────────────────────────────────────────────────────────────────

API_BASE = os.environ.get("CAREOPS_API_BASE", "http://localhost:8000/api/v1")
API_EMAIL = os.environ.get("CAREOPS_EMAIL", "")
API_PASSWORD = os.environ.get("CAREOPS_PASSWORD", "")

SUPPORTED_SCENARIOS = [
    "friday_rush",
    "weekday_lunch",
    "holiday_spike",
    "low_stock_weekend",
]

# ── Server + auth state ───────────────────────────────────────────────────────

server = Server("careops")
_token: str | None = None


async def _get_token() -> str:
    global _token
    if _token:
        return _token
    if not API_EMAIL or not API_PASSWORD:
        raise RuntimeError(
            "CAREOPS_EMAIL and CAREOPS_PASSWORD must be set in the environment."
        )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{API_BASE}/auth/login",
            json={"email": API_EMAIL, "password": API_PASSWORD},
        )
        resp.raise_for_status()
        _token = resp.json()["access_token"]
    return _token


async def _api(method: str, path: str, **kwargs) -> dict:
    token = await _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.request(
            method, f"{API_BASE}{path}", headers=headers, **kwargs
        )
        resp.raise_for_status()
        return resp.json()


# ── Tool definitions ──────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="run_planning_scenario",
            description=(
                "Trigger a CareOps AI multi-agent planning run for a restaurant service scenario. "
                "Returns demand forecast, reservation outlook, complaint analysis, menu insights, "
                "inventory actions, and a critic verdict with score. "
                f"Supported scenarios: {', '.join(SUPPORTED_SCENARIOS)}."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "scenario": {
                        "type": "string",
                        "description": f"Planning scenario to run. One of: {', '.join(SUPPORTED_SCENARIOS)}.",
                        "enum": SUPPORTED_SCENARIOS,
                    },
                    "target_date": {
                        "type": "string",
                        "description": "Optional target date in YYYY-MM-DD format. Defaults to the next matching service day.",
                    },
                    "restaurant_id": {
                        "type": "integer",
                        "description": "Optional restaurant profile ID to use. If omitted, uses default org settings.",
                    },
                },
                "required": ["scenario"],
            },
        ),
        types.Tool(
            name="get_run_history",
            description=(
                "Retrieve recent CareOps AI planning runs with scenario, date, critic verdict, "
                "and score. Optionally filter by scenario or critic verdict."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of runs to return (1–50). Defaults to 10.",
                        "default": 10,
                    },
                    "scenario": {
                        "type": "string",
                        "description": "Filter by scenario ID.",
                        "enum": SUPPORTED_SCENARIOS,
                    },
                    "verdict": {
                        "type": "string",
                        "description": "Filter by critic verdict.",
                        "enum": ["approved", "revision", "rejected"],
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_market_brief",
            description=(
                "Get a live market snapshot: category-level pricing vs the area average, "
                "your competitive positioning, menu breadth, cuisine crowding, veg/non-veg mix, "
                "live competitor deals, and area occupancy tonight."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_action_queue",
            description=(
                "List pending (or other-status) actions in the Action Queue -- e.g. restock "
                "alerts, WhatsApp vendor order drafts awaiting approval, pricing/promo review flags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status. Defaults to 'pending' if omitted.",
                        "enum": ["pending", "approved", "executed", "rejected", "expired"],
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="approve_action",
            description=(
                "Approve a specific Action Queue item by its ID. For a WhatsApp vendor-order "
                "action, this is the same step that actually sends the message -- there's "
                "nothing further to approve once you've confirmed it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "action_id": {
                        "type": "integer",
                        "description": "The ID of the action to approve, from get_action_queue's results.",
                    },
                },
                "required": ["action_id"],
            },
        ),
    ]


# ── Tool handlers ─────────────────────────────────────────────────────────────

@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    if name == "run_planning_scenario":
        return await _handle_run_planning(arguments)
    if name == "get_run_history":
        return await _handle_get_runs(arguments)
    if name == "get_market_brief":
        return await _handle_get_market_brief(arguments)
    if name == "get_action_queue":
        return await _handle_get_action_queue(arguments)
    if name == "approve_action":
        return await _handle_approve_action(arguments)
    raise ValueError(f"Unknown tool: {name}")


async def _handle_run_planning(args: dict) -> list[types.TextContent]:
    scenario = args["scenario"]
    payload: dict[str, Any] = {"scenario": scenario}
    if args.get("target_date"):
        payload["target_date"] = args["target_date"]
    if args.get("restaurant_id"):
        payload["restaurant_id"] = args["restaurant_id"]

    try:
        result = await _api("POST", "/planning/run", json=payload)
    except httpx.HTTPStatusError as exc:
        return [types.TextContent(type="text", text=f"Planning run failed: {exc.response.text}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Planning run failed: {exc}")]

    critic = result.get("critic", {})
    meta = result.get("meta", {})
    recs = result.get("recommendations", {})

    lines = [
        f"# CareOps AI Planning Run — {scenario.replace('_', ' ').title()}",
        f"**Target date:** {result.get('target_date', 'N/A')}",
        f"**Status:** {result.get('status', 'unknown')}",
        "",
        f"## Critic verdict: {critic.get('verdict', 'unknown').upper()} (score {critic.get('score', 0):.2f})",
        f"{critic.get('notes', '')}",
        "",
        "## Demand forecast",
        recs.get("forecast", {}).get("recommendation", "—"),
        "",
        "## Reservations",
        recs.get("reservation", {}).get("recommendation", "—"),
        "",
        "## Complaints",
        recs.get("complaint", {}).get("overall_summary", "—"),
        "",
        "## Menu insights",
        recs.get("menu", {}).get("reasoning", "—"),
        "",
        "## Inventory",
        recs.get("inventory", {}).get("reasoning", "—"),
        "",
        f"**Run ID:** {meta.get('run_id', 'N/A')} | "
        f"**LLM:** {meta.get('llm_provider', 'N/A')}/{meta.get('llm_model', 'N/A')} | "
        f"**Cost:** ${meta.get('total_cost_usd', 0):.4f} | "
        f"**Duration:** {meta.get('total_duration_ms', 0):.0f}ms",
    ]

    return [types.TextContent(type="text", text="\n".join(lines))]


async def _handle_get_runs(args: dict) -> list[types.TextContent]:
    params: dict[str, Any] = {"limit": min(int(args.get("limit", 10)), 50)}
    if args.get("scenario"):
        params["scenario"] = args["scenario"]
    if args.get("verdict"):
        params["verdict"] = args["verdict"]

    try:
        result = await _api("GET", "/runs", params=params)
    except httpx.HTTPStatusError as exc:
        return [types.TextContent(type="text", text=f"Failed to fetch runs: {exc.response.text}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Failed to fetch runs: {exc}")]

    runs = result.get("runs", [])
    if not runs:
        return [types.TextContent(type="text", text="No planning runs found.")]

    lines = ["# CareOps AI — Recent Planning Runs", ""]
    for run in runs:
        critic = run.get("critic_verdict", "unknown")
        score = run.get("critic_score", 0.0)
        lines.append(
            f"- **Run #{run.get('id')}** | {run.get('scenario', '?')} | "
            f"{run.get('target_date', '?')} | "
            f"Verdict: **{critic}** ({score:.2f}) | "
            f"Status: {run.get('status', '?')}"
        )

    lines += ["", f"*{len(runs)} run(s) returned.*"]
    return [types.TextContent(type="text", text="\n".join(lines))]


async def _handle_get_market_brief(args: dict) -> list[types.TextContent]:
    try:
        result = await _api("GET", "/market/pulse")
    except httpx.HTTPStatusError as exc:
        return [types.TextContent(type="text", text=f"Failed to fetch market brief: {exc.response.text}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Failed to fetch market brief: {exc}")]

    if not result.get("swiggy_connected"):
        return [types.TextContent(type="text", text="Swiggy is not connected for this org -- connect it in /connectors to see live market data.")]

    lines = ["# CareOps AI — Live Market Brief", ""]

    pricing = result.get("competitor_pricing") or {}
    category_pricing = pricing.get("category_pricing") or []
    if category_pricing:
        lines.append("## Category pricing (you vs area average)")
        for c in category_pricing:
            lines.append(
                f"- **{c['category']}**: you ₹{c['your_avg']:.0f} vs area ₹{c['area_avg']:.0f} "
                f"({c['verdict']}, {c['diff_pct']:.1f}% diff)"
            )
        lines.append("")

    positioning = pricing.get("positioning")
    if positioning:
        lines.append(
            f"## Positioning: rank {positioning['rank']}/{positioning['total']} "
            f"({positioning['cheaper_than_count']} cheaper than you, "
            f"{positioning['pricier_than_count']} pricier)"
        )
        lines.append("")

    deals_summary = pricing.get("deals_summary")
    if deals_summary:
        lines.append("## Live area deals")
        lines.append(f"- {deals_summary}")
        lines.append("")

    occupancy = result.get("area_occupancy") or {}
    if occupancy.get("signal"):
        busy = " — tonight looks busy" if occupancy.get("tonight_busy") else ""
        lines.append(f"## Area occupancy: {occupancy['signal']}{busy}")
        lines.append("")

    procurement = result.get("procurement") or []
    if procurement:
        lines.append("## Sample ingredient prices (Instamart)")
        for p in procurement[:5]:
            lines.append(f"- {p['name']}: ₹{p['price']:.0f}/{p['unit']}" + ("" if p["in_stock"] else " (out of stock)"))

    return [types.TextContent(type="text", text="\n".join(lines))]


async def _handle_get_action_queue(args: dict) -> list[types.TextContent]:
    params: dict[str, Any] = {}
    if args.get("status"):
        params["status"] = args["status"]

    try:
        actions = await _api("GET", "/action-queue", params=params)
    except httpx.HTTPStatusError as exc:
        return [types.TextContent(type="text", text=f"Failed to fetch Action Queue: {exc.response.text}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Failed to fetch Action Queue: {exc}")]

    if not actions:
        status_label = args.get("status", "pending")
        return [types.TextContent(type="text", text=f"No {status_label} actions in the queue.")]

    lines = ["# CareOps AI — Action Queue", ""]
    for a in actions:
        streak = a.get("approval_streak", 0)
        streak_note = f" (approved {streak}x in a row before)" if streak > 0 else ""
        lines.append(f"- **#{a['id']}** [{a['category']}/{a['tier']}] {a['title']}{streak_note}")

    lines += ["", f"*{len(actions)} action(s) returned. Use approve_action with the ID to approve one.*"]
    return [types.TextContent(type="text", text="\n".join(lines))]


async def _handle_approve_action(args: dict) -> list[types.TextContent]:
    action_id = args.get("action_id")
    if action_id is None:
        return [types.TextContent(type="text", text="action_id is required.")]

    try:
        result = await _api("POST", f"/action-queue/{int(action_id)}/approve")
    except httpx.HTTPStatusError as exc:
        return [types.TextContent(type="text", text=f"Failed to approve action {action_id}: {exc.response.text}")]
    except Exception as exc:
        return [types.TextContent(type="text", text=f"Failed to approve action {action_id}: {exc}")]

    status = result.get("status")
    if status == "executed":
        return [types.TextContent(type="text", text=f"Approved and executed: {result.get('title')}")]
    if result.get("error"):
        return [types.TextContent(type="text", text=f"Approved, but execution failed: {result['error']}")]
    return [types.TextContent(type="text", text=f"Approved: {result.get('title')} (status: {status})")]


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
