"""
CareOps AI Healthcare MCP Server

Exposes local hospital operations tools (replaces Swiggy MCP):
  • get_capacity_snapshot
  • get_department_workload
  • get_staffing_summary
  • get_supply_shortages
  • get_fhir_encounter_summary
  • search_hospital_policy
  • create_review_action
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from app.infrastructure.db.base import SessionLocal
from app.infrastructure.healthcare.mcp_tools import HealthcareMCPTools
from app.infrastructure.vector.embedding_service import EmbeddingService
from app.infrastructure.vector.memory_service import MemoryService
from app.infrastructure.vector.qdrant_client import get_qdrant_client

server = Server("careops-healthcare")


def _tools() -> HealthcareMCPTools:
    db = SessionLocal()
    try:
        memory = MemoryService(get_qdrant_client(), EmbeddingService())
        return HealthcareMCPTools(db, memory=memory)
    except Exception:
        return HealthcareMCPTools(db, memory=None)


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name="get_capacity_snapshot", description="Department bed occupancy snapshot", inputSchema={"type": "object", "properties": {"org_id": {"type": "integer"}}, "required": []}),
        types.Tool(name="get_department_workload", description="48h appointment workload by department", inputSchema={"type": "object", "properties": {"department": {"type": "string"}}, "required": []}),
        types.Tool(name="get_staffing_summary", description="Staff headcount by department and role", inputSchema={"type": "object", "properties": {"org_id": {"type": "integer"}}, "required": []}),
        types.Tool(name="get_supply_shortages", description="Operational supplies below reorder threshold", inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="get_fhir_encounter_summary", description="Synthetic FHIR encounter aggregates (no PHI)", inputSchema={"type": "object", "properties": {}}),
        types.Tool(name="search_hospital_policy", description="Search hospital SOPs with citations", inputSchema={"type": "object", "properties": {"query": {"type": "string"}, "org_id": {"type": "integer"}, "top_k": {"type": "integer"}}, "required": ["query"]}),
        types.Tool(name="create_review_action", description="Create human-reviewed operations action", inputSchema={"type": "object", "properties": {"org_id": {"type": "integer"}, "title": {"type": "string"}, "description": {"type": "string"}, "confidence": {"type": "number"}}, "required": ["org_id", "title", "description"]}),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    tools = _tools()
    org_id = arguments.get("org_id", 1)
    if name == "get_capacity_snapshot":
        result = tools.get_capacity_snapshot(org_id=org_id)
    elif name == "get_department_workload":
        result = tools.get_department_workload(arguments.get("department"))
    elif name == "get_staffing_summary":
        result = tools.get_staffing_summary(org_id=org_id)
    elif name == "get_supply_shortages":
        result = tools.get_supply_shortages()
    elif name == "get_fhir_encounter_summary":
        result = tools.get_fhir_encounter_summary()
    elif name == "search_hospital_policy":
        result = tools.search_hospital_policy(arguments["query"], org_id=org_id, top_k=arguments.get("top_k", 3))
    elif name == "create_review_action":
        result = tools.create_review_action(org_id=org_id, title=arguments["title"], description=arguments["description"], confidence=arguments.get("confidence", 0.5))
    else:
        raise ValueError(f"Unknown tool: {name}")
    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
