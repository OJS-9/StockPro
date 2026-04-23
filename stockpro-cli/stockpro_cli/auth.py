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


@click.group()
def auth():
    """Manage authentication."""
    pass


@auth.command()
@click.pass_context
def login(ctx):
    """Authenticate via browser sign-in."""
    api_url = ctx.obj.get("api_url") or get_api_url()

    server = HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = server.server_address[1]

    url = f"{api_url}/cli/auth?port={port}"
    click.echo(f"Opening browser for sign-in...", err=True)
    webbrowser.open(url)

    server.handle_request()

    if _CallbackHandler.token:
        cfg = load_config()
        cfg["access_token"] = _CallbackHandler.token
        if ctx.obj.get("api_url"):
            cfg["api_url"] = ctx.obj["api_url"]
        save_config(cfg)
        output({"status": "authenticated"}, ctx.obj.get("pretty", False))
    else:
        json.dump({"error": "Authentication failed -- no token received"}, sys.stderr)
        sys.stderr.write("\n")
        sys.exit(1)


@auth.command("device-login")
@click.pass_context
def device_login(ctx):
    """Authenticate headlessly via device code (no browser on this machine)."""
    api_url = (ctx.obj.get("api_url") or get_api_url()).rstrip("/")

    try:
        resp = httpx.post(f"{api_url}/api/device/authorize", timeout=30.0)
    except httpx.HTTPError as exc:
        json.dump({"error": f"Failed to reach {api_url}: {exc}"}, sys.stderr)
        sys.stderr.write("\n")
        sys.exit(1)

    if resp.status_code != 200:
        json.dump({"error": f"authorize failed ({resp.status_code}): {resp.text[:200]}"}, sys.stderr)
        sys.stderr.write("\n")
        sys.exit(1)

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
    while time.time() < deadline:
        time.sleep(interval)
        try:
            poll = httpx.post(
                f"{api_url}/api/device/token",
                json={"device_code": device_code},
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            json.dump({"error": f"poll failed: {exc}"}, sys.stderr)
            sys.stderr.write("\n")
            sys.exit(1)

        if poll.status_code == 429:
            interval = min(interval * 2, 30)
            continue

        body = poll.json() if poll.content else {}
        status_value = body.get("status")

        if status_value == "pending":
            continue
        if status_value == "expired":
            json.dump({"error": "Device code expired. Run again."}, sys.stderr)
            sys.stderr.write("\n")
            sys.exit(1)
        if status_value == "approved" and body.get("access_token"):
            cfg = load_config()
            cfg["access_token"] = body["access_token"]
            if ctx.obj.get("api_url"):
                cfg["api_url"] = ctx.obj["api_url"]
            save_config(cfg)
            output({"status": "authenticated"}, ctx.obj.get("pretty", False))
            return

    json.dump({"error": "Device code expired before approval."}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


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
