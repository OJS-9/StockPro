"""Watchlist commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.exchanges import EXCHANGES, apply_exchange_suffix
from stockpro_cli.output import output


@click.group()
def watchlist():
    """Manage watchlists."""
    pass


@watchlist.command("list")
@click.option("--wl", default=None, help="Watchlist ID to filter")
@click.pass_context
def list_watchlists(ctx, wl):
    """List watchlists."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if wl:
        params["wl"] = wl
    data = client.get("/api/watchlists", params=params)
    output(data, ctx.obj.get("pretty", False))


@watchlist.command("add-symbol")
@click.option("--id", "watchlist_id", required=True, help="Watchlist ID")
@click.option("--symbol", required=True, help="Ticker symbol (or symbol.TA for TASE)")
@click.option("--exchange", default="US", type=click.Choice(EXCHANGES, case_sensitive=False), help="US (default) or TASE")
@click.pass_context
def add_symbol(ctx, watchlist_id, symbol, exchange):
    """Add a symbol to a watchlist."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.post(f"/api/watchlist/{watchlist_id}/symbol", {"symbol": apply_exchange_suffix(symbol, exchange)})
    output(data, ctx.obj.get("pretty", False))


@watchlist.command("remove-item")
@click.option("--id", "item_id", required=True, help="Watchlist item ID")
@click.pass_context
def remove_item(ctx, item_id):
    """Remove an item from a watchlist."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.delete(f"/api/watchlist/item/{item_id}")
    output(data, ctx.obj.get("pretty", False))


@watchlist.command("toggle-pin")
@click.option("--id", "item_id", required=True, help="Watchlist item ID")
@click.pass_context
def toggle_pin(ctx, item_id):
    """Toggle pin status of a watchlist item."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.patch(f"/api/watchlist/item/{item_id}/pin")
    output(data, ctx.obj.get("pretty", False))


@watchlist.command("news")
@click.option("--id", "watchlist_id", required=True, help="Watchlist ID")
@click.pass_context
def news(ctx, watchlist_id):
    """Get news recap for a watchlist."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/watchlist/{watchlist_id}/news-recap")
    output(data, ctx.obj.get("pretty", False))


@watchlist.command("earnings")
@click.option("--id", "watchlist_id", required=True, help="Watchlist ID")
@click.pass_context
def earnings(ctx, watchlist_id):
    """Get earnings calendar for a watchlist."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/watchlist/{watchlist_id}/earnings")
    output(data, ctx.obj.get("pretty", False))


@watchlist.command("delete-all")
@click.option("--confirm", is_flag=True, required=True, help="Confirm deletion")
@click.pass_context
def delete_all(ctx, confirm):
    """Delete all watchlists. Requires --confirm."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.delete("/api/watchlists/all")
    output(data, ctx.obj.get("pretty", False))
