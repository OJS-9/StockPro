"""Login/logout/status via browser OAuth + localhost callback."""

import click
import json
import sys
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
