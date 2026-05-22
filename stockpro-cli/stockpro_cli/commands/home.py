"""Home dashboard command."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.output import output


@click.command()
@click.pass_context
def home(ctx):
    """Get home dashboard data."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/home")
    output(data, ctx.obj.get("pretty", False))
