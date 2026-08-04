"""Unit tests for SwiggyMCPClient.

All tests mock httpx — no real HTTP calls. Verifies:
- Graceful degradation: every failure path returns None and never raises.
- Correct Accept header sent on every request.
- New JSON-RPC response parsing (result.structuredContent / content[0].text).
- JSON-RPC error at top level returns None.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.infrastructure.swiggy.client import SwiggyMCPClient, FOOD_ENDPOINT


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(status_code: int, body: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {}
    return resp


def _mock_httpx(mock_response):
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_ctx.post = AsyncMock(return_value=mock_response)
    return mock_ctx


# ── Basic availability ─────────────────────────────────────────────────────────

def test_is_available_true():
    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings:
        mock_settings.return_value.swiggy_access_token = "tok_abc123"
        client = SwiggyMCPClient()
        assert client.is_available() is True


def test_is_available_false():
    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings:
        mock_settings.return_value.swiggy_access_token = ""
        client = SwiggyMCPClient()
        assert client.is_available() is False


# ── HTTP error handling ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_returns_none_on_401():
    client = SwiggyMCPClient()
    mock_ctx = _mock_httpx(_make_response(401))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result is None


@pytest.mark.asyncio
async def test_call_tool_returns_none_on_406():
    client = SwiggyMCPClient()
    mock_ctx = _mock_httpx(_make_response(406))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result is None


@pytest.mark.asyncio
async def test_call_tool_returns_none_on_500_after_retry():
    client = SwiggyMCPClient()
    mock_ctx = _mock_httpx(_make_response(500))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result is None
    assert mock_ctx.post.call_count == 2


# ── New JSON-RPC response parsing ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_returns_structured_content():
    client = SwiggyMCPClient()
    body = {
        "result": {
            "content": [{"type": "text", "text": "..."}],
            "structuredContent": {"addresses": [{"id": "addr_01", "label": "Home"}]},
        },
        "jsonrpc": "2.0",
        "id": 1,
    }
    mock_ctx = _mock_httpx(_make_response(200, body))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result == {"addresses": [{"id": "addr_01", "label": "Home"}]}


@pytest.mark.asyncio
async def test_call_tool_falls_back_to_text_content():
    client = SwiggyMCPClient()
    body = {
        "result": {
            "content": [{"type": "text", "text": "some plain text response"}],
        },
        "jsonrpc": "2.0",
        "id": 1,
    }
    mock_ctx = _mock_httpx(_make_response(200, body))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result == {"text": "some plain text response"}


@pytest.mark.asyncio
async def test_call_tool_returns_none_on_jsonrpc_error():
    client = SwiggyMCPClient()
    body = {
        "error": {"code": -32601, "message": "Tool not found"},
        "jsonrpc": "2.0",
        "id": 1,
    }
    mock_ctx = _mock_httpx(_make_response(200, body))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result is None


@pytest.mark.asyncio
async def test_call_tool_returns_none_when_no_result_key():
    client = SwiggyMCPClient()
    body = {"jsonrpc": "2.0", "id": 1}
    mock_ctx = _mock_httpx(_make_response(200, body))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result is None


# ── Accept header ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_sends_accept_header():
    client = SwiggyMCPClient()
    body = {
        "result": {"structuredContent": {"addresses": []}},
        "jsonrpc": "2.0",
        "id": 1,
    }
    mock_ctx = _mock_httpx(_make_response(200, body))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok_xyz"
        await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    call_kwargs = mock_ctx.post.call_args
    headers_sent = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert headers_sent.get("Accept") == "application/json, text/event-stream"


# ── Never raises ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_tool_never_raises():
    client = SwiggyMCPClient()
    mock_ctx = AsyncMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_ctx.post = AsyncMock(side_effect=Exception("network failure"))

    with patch("app.infrastructure.swiggy.client.get_settings") as mock_settings, \
         patch("httpx.AsyncClient", return_value=mock_ctx):
        mock_settings.return_value.swiggy_access_token = "tok"
        result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})

    assert result is None
