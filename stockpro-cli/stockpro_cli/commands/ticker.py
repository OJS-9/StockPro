"""Ticker data commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.exchanges import EXCHANGES, apply_exchange_suffix
from stockpro_cli.output import output


@click.group()
def ticker():
    """Look up ticker data."""
    pass


@ticker.command("history")
@click.option("--symbol", required=True, help="Ticker symbol (or symbol.TA for TASE)")
@click.option("--exchange", default="US", type=click.Choice(EXCHANGES, case_sensitive=False), help="US (default) or TASE")
@click.option("--range", "time_range", default=None, help="Time range (e.g. 1m, 3m, 1y)")
@click.pass_context
def history(ctx, symbol, exchange, time_range):
    """Get price history for a ticker."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if time_range:
        params["range"] = time_range
    data = client.get(f"/api/ticker/{apply_exchange_suffix(symbol, exchange)}/history", params=params)
    output(data, ctx.obj.get("pretty", False))


@ticker.command("fundamentals")
@click.option("--symbol", required=True, help="Ticker symbol (or symbol.TA for TASE)")
@click.option("--exchange", default="US", type=click.Choice(EXCHANGES, case_sensitive=False), help="US (default) or TASE")
@click.pass_context
def fundamentals(ctx, symbol, exchange):
    """Get fundamental data for a ticker."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/ticker/{apply_exchange_suffix(symbol, exchange)}/fundamentals")
    output(data, ctx.obj.get("pretty", False))


@ticker.command("search")
@click.option("--query", required=True, help="Search query")
@click.pass_context
def search(ctx, query):
    """Search for tickers."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/ticker/search", params={"q": query})
    output(data, ctx.obj.get("pretty", False))


@ticker.command("recent")
@click.pass_context
def recent(ctx):
    """Get recently viewed tickers."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/tickers/recent")
    output(data, ctx.obj.get("pretty", False))
