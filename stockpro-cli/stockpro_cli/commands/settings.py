"""User settings commands."""

import json
import click
from stockpro_cli.client import get_client
from stockpro_cli.output import output


@click.group()
def settings():
    """Manage user settings."""
    pass


@settings.command("get")
@click.pass_context
def get_settings(ctx):
    """Get current settings."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/settings")
    output(data, ctx.obj.get("pretty", False))


@settings.command("update")
@click.option("--display-name", default=None, help="Display name")
@click.option("--json-data", default=None, help="Arbitrary settings as JSON string")
@click.pass_context
def update_settings(ctx, display_name, json_data):
    """Update user settings."""
    client = get_client(ctx.obj.get("api_url"))
    payload = {}
    if display_name:
        payload["display_name"] = display_name
    if json_data:
        payload.update(json.loads(json_data))
    data = client.put("/api/settings", payload)
    output(data, ctx.obj.get("pretty", False))
