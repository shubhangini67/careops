"""
One-command Swiggy OAuth 2.1 PKCE flow.

Usage:
    python scripts/get_swiggy_token.py

What it does:
1. Generates PKCE verifier + challenge
2. Starts a local HTTP server on port 8080 to catch the callback
3. Opens your browser to Swiggy's authorize URL (phone + OTP)
4. Waits up to 120 seconds for the callback
5. Exchanges the code for an access token
6. Saves SWIGGY_ACCESS_TOKEN and SWIGGY_ADDRESS_ID to apps/api/.env automatically
"""

import asyncio
import base64
import hashlib
import json
import pathlib
import secrets
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
AUTH_BASE = "https://mcp.swiggy.com"
CALLBACK_PORT = 8080
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
CLIENT_ID = "swiggy-mcp"
SCOPE = "mcp:tools"
STATE = "careops-local"
TIMEOUT_SECONDS = 120

# .env is two levels up from scripts/
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_PATH = _REPO_ROOT / "apps" / "api" / ".env"

# ---------------------------------------------------------------------------
# PKCE
# ---------------------------------------------------------------------------
code_verifier = secrets.token_urlsafe(32)
code_challenge = base64.urlsafe_b64encode(
    hashlib.sha256(code_verifier.encode()).digest()
).rstrip(b"=").decode()

# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------
_callback_result: dict = {}
_server_ready = threading.Event()


class _CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence access logs

    def do_GET(self):
        if self.path.startswith("/callback"):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            _callback_result["code"] = (params.get("code") or [None])[0]
            _callback_result["state"] = (params.get("state") or [None])[0]
            _callback_result["error"] = (params.get("error") or [None])[0]

            body = b"<html><body><h2>CareOps AI: authentication complete.</h2><p>You can close this tab.</p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            threading.Thread(target=self.server.shutdown, daemon=True).start()
        else:
            self.send_response(404)
            self.end_headers()


def _run_server(server: HTTPServer):
    _server_ready.set()
    server.serve_forever()


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------
def _read_env() -> str:
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8")
    return ""


def _set_env_key(contents: str, key: str, value: str) -> str:
    lines = contents.splitlines(keepends=True)
    new_line = f"{key}={value}\n"
    for i, line in enumerate(lines):
        if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
            lines[i] = new_line
            return "".join(lines)
    # key not found — append
    if contents and not contents.endswith("\n"):
        return contents + "\n" + new_line
    return contents + new_line


def _save_env(contents: str):
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text(contents, encoding="utf-8")


# ---------------------------------------------------------------------------
# get_addresses via Food MCP
# ---------------------------------------------------------------------------
async def _get_addresses(access_token: str) -> list:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AUTH_BASE}/food",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": "get_addresses", "arguments": {}},
                "id": 1,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    result = data.get("result", {})
    structured = result.get("structuredContent", {})
    return structured.get("addresses", [])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    # 1. Start local callback server
    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    server_thread = threading.Thread(target=_run_server, args=(server,), daemon=True)
    server_thread.start()
    _server_ready.wait(timeout=5)

    # 2. Build authorize URL and open browser
    authorize_url = (
        f"{AUTH_BASE}/auth/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&state={STATE}"
        f"&scope={SCOPE}"
    )
    print(f"\nOpening browser for Swiggy login...")
    print(f"URL: {authorize_url}\n")
    webbrowser.open(authorize_url)

    # 3. Wait for callback
    print("Waiting for Swiggy login (timeout: 120 seconds)...")
    deadline = time.time() + TIMEOUT_SECONDS
    while not _callback_result and time.time() < deadline:
        time.sleep(0.5)

    if not _callback_result:
        print("\nERROR: Timed out waiting for OAuth callback.", file=sys.stderr)
        sys.exit(1)

    if _callback_result.get("error"):
        print(f"\nERROR: OAuth error — {_callback_result['error']}", file=sys.stderr)
        sys.exit(1)

    received_code = _callback_result.get("code")
    if not received_code:
        print("\nERROR: No authorization code in callback.", file=sys.stderr)
        sys.exit(1)

    print(f"Callback received. Exchanging code for token...")

    # 4. Exchange code for token
    payload = json.dumps({
        "grant_type": "authorization_code",
        "code": received_code,
        "code_verifier": code_verifier,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
    }).encode()

    req = urllib.request.Request(
        f"{AUTH_BASE}/auth/token",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            token_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"\nERROR: Token exchange failed ({e.code}): {body}", file=sys.stderr)
        sys.exit(1)

    access_token = token_data.get("access_token")
    if not access_token:
        print(f"\nERROR: No access_token in response: {token_data}", file=sys.stderr)
        sys.exit(1)

    expires_in = token_data.get("expires_in", 432000)

    # 5. Print token
    print("\n" + "=" * 60)
    print("SWIGGY ACCESS TOKEN:")
    print(access_token)
    print("=" * 60)
    print(f"Expires in: {expires_in // 86400} days")

    # 6. Save token to .env
    env_contents = _read_env()
    env_contents = _set_env_key(env_contents, "SWIGGY_ACCESS_TOKEN", access_token)
    _save_env(env_contents)
    print(f"\nToken saved to {ENV_PATH}")

    # 7. Fetch and save address ID
    print("\nFetching your Swiggy address ID...")
    try:
        addresses = asyncio.run(_get_addresses(access_token))
    except Exception as e:
        print(f"WARNING: Could not fetch addresses: {e}")
        addresses = []

    if addresses:
        address_id = addresses[0]["id"]
        label = addresses[0].get("label", "Home")
        display = addresses[0].get("displayText", addresses[0].get("addressLine", ""))
        print(f"\nYour address ID: {address_id}")
        print(f"Label: {label}")
        if display:
            print(f"Address: {display}")

        env_contents = _read_env()
        env_contents = _set_env_key(env_contents, "SWIGGY_ADDRESS_ID", address_id)
        _save_env(env_contents)
        print("Address ID saved to .env automatically.")
    else:
        print("No addresses found. Add an address in your Swiggy app first.")

    print("\nDone. Restart your API server to pick up the new .env values.")


if __name__ == "__main__":
    main()
