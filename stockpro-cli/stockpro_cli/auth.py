"""Login/logout/status via browser OAuth + localhost callback."""

import click
import httpx
import json
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from stockpro_cli.config import load_config, save_config, get_api_url, get_token, clear_auth
from stockpro_cli.client import StockProClient
from stockpro_cli.output import output
from stockpro_cli.keychain import store_token

_LOGIN_TIMEOUT_SECONDS = 120


class _CallbackHandler(BaseHTTPRequestHandler):
    token = None

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            token = params.get("token", [None])[0]
            if token:
                _CallbackHandler.token = token
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Authenticated! You can close this tab.</h2></body></html>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing token")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


def _stderr_error(payload: dict, exit_code: int = 1):
    click.echo(json.dumps(payload), err=True)
    sys.exit(exit_code)


@click.group()
def auth():
    """Manage authentication."""
    pass


@auth.command()
@click.pass_context
def login(ctx):
    """Authenticate via browser sign-in."""
    api_url = ctx.obj.get("api_url") or get_api_url()

    # Reset class-level token between invocations.
    _CallbackHandler.token = None

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    server.timeout = 1  # short per-call so we can poll the wall-clock deadline
    port = server.server_address[1]

    url = f"{api_url}/cli/auth?port={port}"
    click.echo("Opening browser for sign-in...", err=True)
    webbrowser.open(url)

    deadline = time.monotonic() + _LOGIN_TIMEOUT_SECONDS
    try:
        while _CallbackHandler.token is None and time.monotonic() < deadline:
            server.handle_request()
    except KeyboardInterrupt:
        server.server_close()
        _stderr_error({"error": "Login cancelled by user"}, exit_code=130)
    except Exception as exc:
        server.server_close()
        _stderr_error({"error": f"Login failed: {exc}"})
    finally:
        server.server_close()

    if _CallbackHandler.token:
        store_token(_CallbackHandler.token)
        if ctx.obj.get("api_url"):
            cfg = load_config()
            cfg["api_url"] = ctx.obj["api_url"]
            save_config(cfg)
        output({"status": "authenticated"}, ctx.obj.get("pretty", False))
    else:
        _stderr_error(
            {
                "error": "Authentication timed out -- no token received",
                "timeout_seconds": _LOGIN_TIMEOUT_SECONDS,
            }
        )


@auth.command("device-login")
@click.pass_context
def device_login(ctx):
    """Authenticate headlessly via device code (no browser on this machine)."""
    api_url = (ctx.obj.get("api_url") or get_api_url()).rstrip("/")

    try:
        resp = httpx.post(f"{api_url}/api/device/authorize", timeout=30.0)
    except httpx.HTTPError as exc:
        _stderr_error({"error": f"Failed to reach {api_url}: {exc}"})

    if resp.status_code != 200:
        _stderr_error(
            {"error": f"authorize failed ({resp.status_code}): {resp.text[:200]}"}
        )

    data = resp.json()
    device_code = data["device_code"]
    user_code = data["user_code"]
    verification_uri = data["verification_uri"]
    expires_in = int(data.get("expires_in", 600))
    interval = max(1, int(data.get("interval", 5)))

    click.echo(
        f"Open {verification_uri}?user_code={user_code} on any browser,\n"
        f"sign in, and confirm code: {user_code}\n"
        f"(expires in {expires_in // 60} min). Waiting...",
        err=True,
    )

    deadline = time.time() + expires_in
    try:
        while time.time() < deadline:
            time.sleep(interval)
            try:
                poll = httpx.post(
                    f"{api_url}/api/device/token",
                    json={"device_code": device_code},
                    timeout=30.0,
                )
            except httpx.HTTPError as exc:
                _stderr_error({"error": f"poll failed: {exc}"})

            if poll.status_code == 429:
                interval = min(interval * 2, 30)
                continue

            body = poll.json() if poll.content else {}
            status_value = body.get("status")

            if status_value == "pending":
                continue
            if status_value == "expired":
                _stderr_error({"error": "Device code expired. Run again."})
            if status_value == "approved" and body.get("access_token"):
                store_token(body["access_token"])
                if ctx.obj.get("api_url"):
                    cfg = load_config()
                    cfg["api_url"] = ctx.obj["api_url"]
                    save_config(cfg)
                output({"status": "authenticated"}, ctx.obj.get("pretty", False))
                return
    except KeyboardInterrupt:
        _stderr_error({"error": "Device login cancelled by user"}, exit_code=130)

    _stderr_error({"error": "Device code expired before approval."})


@auth.command()
@click.pass_context
def logout(ctx):
    """Clear cached authentication token."""
    clear_auth()
    output({"status": "logged_out"}, ctx.obj.get("pretty", False))


@auth.command()
@click.pass_context
def status(ctx):
    """Check if currently authenticated."""
    token = get_token()
    if not token:
        output({"authenticated": False}, ctx.obj.get("pretty", False))
        return

    api_url = ctx.obj.get("api_url") or get_api_url()
    try:
        client = StockProClient(api_url, token)
        data = client.get("/api/settings")
        output({"authenticated": True, **data}, ctx.obj.get("pretty", False))
    except SystemExit:
        output({"authenticated": False, "reason": "token_expired"}, ctx.obj.get("pretty", False))
