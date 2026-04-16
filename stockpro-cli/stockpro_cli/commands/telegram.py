"""Telegram integration commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.output import output


@click.group()
def telegram():
    """Manage Telegram integration."""
    pass


@telegram.command("connect")
@click.pass_context
def connect(ctx):
    """Get a connect token to link Telegram."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/telegram/connect-token")
    output(data, ctx.obj.get("pretty", False))


@telegram.command("disconnect")
@click.pass_context
def disconnect(ctx):
    """Disconnect Telegram."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.post("/api/telegram/disconnect")
    output(data, ctx.obj.get("pretty", False))


@telegram.command("test")
@click.pass_context
def test(ctx):
    """Send a test message to Telegram."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.post("/api/telegram/test-message")
    output(data, ctx.obj.get("pretty", False))


@telegram.command("status")
@click.pass_context
def status(ctx):
    """Check Telegram connection status."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/telegram/status")
    output(data, ctx.obj.get("pretty", False))
