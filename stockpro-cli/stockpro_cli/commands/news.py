"""News commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.output import output


@click.command()
@click.option("--more", is_flag=True, help="Get extended news")
@click.pass_context
def news(ctx, more):
    """Get market news."""
    client = get_client(ctx.obj.get("api_url"))
    path = "/api/news/more" if more else "/api/news"
    data = client.get(path)
    output(data, ctx.obj.get("pretty", False))
