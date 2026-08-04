"""Swiggy MCP HTTP client.

Handles JSON-RPC 2.0 calls to all three Swiggy MCP servers (Food, Instamart,
Dineout). Graceful degradation is the primary contract: every failure path
returns None and logs — it never raises, so callers don't need try/except.

Observability:
  - Per-call traces accumulated in self._traces; drain via drain_traces().
  - Circuit breaker per endpoint (Redis-backed): 3 failures in 5 min → open
    for 30 min. Open circuit short-circuits to None immediately (no HTTP call).
"""

import asyncio
import time
import structlog

import httpx

from app.core.settings import get_settings

log = structlog.get_logger()

FOOD_ENDPOINT      = "https://mcp.swiggy.com/food"
INSTAMART_ENDPOINT = "https://mcp.swiggy.com/im"
DINEOUT_ENDPOINT   = "https://mcp.swiggy.com/dineout"

_TIMEOUT  = 30.0
_PROVIDER = "swiggy"


class SwiggyMCPClient:
    """Low-level JSON-RPC client for all three Swiggy MCP servers.

    Instantiate once per request or share across enrichers — it holds no
    mutable per-call state except _traces. Token is read from settings on
    each call so it stays fresh if the caller updates settings between calls.
    """

    def __init__(self) -> None:
        self._traces: list[dict] = []

    def drain_traces(self) -> list[dict]:
        """Return and clear accumulated call traces."""
        traces, self._traces = self._traces, []
        return traces

    def is_available(self) -> bool:
        """True when a token is configured and non-empty."""
        return bool(get_settings().swiggy_access_token)

    async def call_tool(
        self,
        endpoint: str,
        tool_name: str,
        arguments: dict,
    ) -> dict | None:
        """POST a JSON-RPC tools/call and return the data payload.

        Returns None on any failure (401, 5xx, network error, bad response,
        or open circuit). Retries once on 5xx after a 1-second sleep. Never raises.
        """
        from app.infrastructure.swiggy.circuit_breaker import (
            is_open, record_failure, record_success,
        )

        token      = get_settings().swiggy_access_token
        server_tag = endpoint.rstrip("/").rsplit("/", 1)[-1]

        # ── Circuit breaker check ────────────────────────────────────────────
        if await is_open(_PROVIDER, server_tag):
            log.warning(
                "swiggy_circuit_open_skipping",
                tool=tool_name,
                server=server_tag,
            )
            self._traces.append({
                "provider":    _PROVIDER,
                "endpoint":    server_tag,
                "tool":        tool_name,
                "status":      "circuit_open",
                "duration_ms": 0,
            })
            return None

        payload = {
            "jsonrpc": "2.0",
            "method":  "tools/call",
            "params":  {"name": tool_name, "arguments": arguments},
            "id":      1,
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "Accept":        "application/json, text/event-stream",
        }

        result = await self._post(
            endpoint, payload, headers, tool_name, server_tag, attempt=1
        )

        if result is None:
            await record_failure(_PROVIDER, server_tag)
        else:
            await record_success(_PROVIDER, server_tag)

        return result

    async def _post(
        self,
        endpoint: str,
        payload: dict,
        headers: dict,
        tool_name: str,
        server_tag: str,
        attempt: int,
    ) -> dict | None:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

            duration_ms = round((time.perf_counter() - t0) * 1000, 1)

            if response.status_code == 401:
                log.warning(
                    "swiggy_token_expired",
                    tool=tool_name,
                    server=server_tag,
                    detail="Swiggy token expired or invalid -- re-authentication needed",
                )
                self._traces.append({
                    "provider": _PROVIDER, "endpoint": server_tag,
                    "tool": tool_name, "status": "auth_error",
                    "duration_ms": duration_ms, "attempt": attempt,
                })
                return None

            if response.status_code == 406:
                log.warning(
                    "swiggy_406_not_acceptable",
                    tool=tool_name,
                    server=server_tag,
                    detail="Accept header missing or wrong -- should be 'application/json, text/event-stream'",
                )
                self._traces.append({
                    "provider": _PROVIDER, "endpoint": server_tag,
                    "tool": tool_name, "status": "http_406",
                    "duration_ms": duration_ms, "attempt": attempt,
                })
                return None

            if response.status_code >= 500:
                if attempt == 1:
                    log.warning(
                        "swiggy_5xx_retrying",
                        tool=tool_name, server=server_tag,
                        status=response.status_code, attempt=attempt,
                    )
                    await asyncio.sleep(1)
                    return await self._post(
                        endpoint, payload, headers, tool_name, server_tag, attempt=2
                    )
                log.error(
                    "swiggy_5xx_failed",
                    tool=tool_name, server=server_tag,
                    status=response.status_code, duration_ms=duration_ms,
                )
                self._traces.append({
                    "provider": _PROVIDER, "endpoint": server_tag,
                    "tool": tool_name, "status": f"http_{response.status_code}",
                    "duration_ms": duration_ms, "attempt": attempt,
                })
                return None

            body = response.json()

            # JSON-RPC error at top level
            if "error" in body:
                err = body["error"]
                err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                log.warning(
                    "swiggy_tool_error",
                    tool=tool_name, server=server_tag,
                    error=err_msg, duration_ms=duration_ms,
                )
                self._traces.append({
                    "provider": _PROVIDER, "endpoint": server_tag,
                    "tool": tool_name, "status": "tool_error",
                    "error": err_msg,
                    "duration_ms": duration_ms, "attempt": attempt,
                })
                return None

            if "result" not in body:
                log.warning(
                    "swiggy_no_result_key",
                    tool=tool_name, server=server_tag, duration_ms=duration_ms,
                )
                self._traces.append({
                    "provider": _PROVIDER, "endpoint": server_tag,
                    "tool": tool_name, "status": "tool_error",
                    "error": "no result key in response",
                    "duration_ms": duration_ms, "attempt": attempt,
                })
                return None

            result = body["result"]

            # Prefer structuredContent (machine-readable) -- but only when it's
            # actually populated. Some Dineout tools (confirmed live:
            # search_restaurants_dineout) return structuredContent: {} and put
            # everything in the text content instead, meant for an LLM to read;
            # treating an empty dict as "success with no data" would silently
            # discard the only data actually returned.
            if result.get("structuredContent"):
                log.info("swiggy_tool_ok", tool=tool_name, server=server_tag, duration_ms=duration_ms)
                self._traces.append({
                    "provider":    _PROVIDER,
                    "endpoint":    server_tag,
                    "tool":        tool_name,
                    "status":      "ok",
                    "duration_ms": duration_ms,
                    "attempt":     attempt,
                })
                payload = dict(result["structuredContent"])
                if "_meta" in result:
                    payload["_meta"] = result["_meta"]
                return payload

            # Fallback: plain text content
            content = result.get("content", [])
            if content and content[0].get("type") == "text":
                log.info("swiggy_tool_ok", tool=tool_name, server=server_tag, duration_ms=duration_ms)
                self._traces.append({
                    "provider":    _PROVIDER,
                    "endpoint":    server_tag,
                    "tool":        tool_name,
                    "status":      "ok",
                    "duration_ms": duration_ms,
                    "attempt":     attempt,
                })
                payload = {"text": content[0]["text"]}
                if "_meta" in result:
                    payload["_meta"] = result["_meta"]
                return payload

            log.warning(
                "swiggy_empty_result",
                tool=tool_name, server=server_tag, duration_ms=duration_ms,
            )
            self._traces.append({
                "provider": _PROVIDER, "endpoint": server_tag,
                "tool": tool_name, "status": "tool_error",
                "error": "result has neither structuredContent nor text content",
                "duration_ms": duration_ms, "attempt": attempt,
            })
            return None

        except Exception as exc:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            log.error(
                "swiggy_tool_exception",
                tool=tool_name, server=server_tag,
                error=str(exc), duration_ms=duration_ms,
            )
            self._traces.append({
                "provider":    _PROVIDER,
                "endpoint":    server_tag,
                "tool":        tool_name,
                "status":      "exception",
                "error":       str(exc),
                "duration_ms": duration_ms,
                "attempt":     attempt,
            })
            return None


if __name__ == "__main__":
    import asyncio

    async def smoke():
        from app.core.settings import get_settings
        s = get_settings()
        print(f"Token set: {bool(s.swiggy_access_token)}")
        print(f"Address ID: {s.swiggy_address_id}")
        client = SwiggyMCPClient()
        print(f"Available: {client.is_available()}")
        if client.is_available():
            result = await client.call_tool(FOOD_ENDPOINT, "get_addresses", {})
            print(f"get_addresses result: {result}")

    asyncio.run(smoke())
