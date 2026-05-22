"""Portfolio management commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.exchanges import EXCHANGES, apply_exchange_suffix
from stockpro_cli.output import output


@click.group()
def portfolio():
    """Manage portfolios and holdings."""
    pass


@portfolio.command("list")
@click.pass_context
def list_portfolios(ctx):
    """List all portfolios with current prices."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/portfolios/prices")
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("get")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.pass_context
def get_portfolio(ctx, portfolio_id):
    """Get a single portfolio."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/portfolio/{portfolio_id}")
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("add-transaction")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.option("--symbol", required=True, help="Ticker symbol (or symbol.TA for TASE)")
@click.option("--exchange", default="US", type=click.Choice(EXCHANGES, case_sensitive=False), help="US (default) or TASE. TASE prices must be in ILS.")
@click.option("--type", "tx_type", required=True, type=click.Choice(["buy", "sell"]))
@click.option("--shares", required=True, type=float)
@click.option("--price", required=True, type=float)
@click.option("--date", default=None, help="Transaction date (YYYY-MM-DD)")
@click.option("--notes", default=None)
@click.pass_context
def add_transaction(ctx, portfolio_id, symbol, exchange, tx_type, shares, price, date, notes):
    """Add a buy/sell transaction."""
    client = get_client(ctx.obj.get("api_url"))
    payload = {
        "symbol": apply_exchange_suffix(symbol, exchange),
        "type": tx_type,
        "shares": shares,
        "price": price,
    }
    if date:
        payload["date"] = date
    if notes:
        payload["notes"] = notes
    data = client.post(f"/api/portfolio/{portfolio_id}/transaction", payload)
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("delete-transaction")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.option("--transaction-id", required=True, help="Transaction ID")
@click.pass_context
def delete_transaction(ctx, portfolio_id, transaction_id):
    """Delete a transaction."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.delete(f"/api/portfolio/{portfolio_id}/transaction/{transaction_id}")
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("prices")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.pass_context
def prices(ctx, portfolio_id):
    """Get current prices for portfolio holdings."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/portfolio/{portfolio_id}/prices")
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("history")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.option("--range", "time_range", default=None, help="Time range (e.g. 1m, 3m, 1y)")
@click.pass_context
def history(ctx, portfolio_id, time_range):
    """Get portfolio value history."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if time_range:
        params["range"] = time_range
    data = client.get(f"/api/portfolio/{portfolio_id}/history", params=params)
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("analytics")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.option("--range", "time_range", default=None, help="Time range")
@click.pass_context
def analytics(ctx, portfolio_id, time_range):
    """Get portfolio analytics."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if time_range:
        params["range"] = time_range
    data = client.get(f"/api/portfolio/{portfolio_id}/analytics", params=params)
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("transactions")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.option("--limit", default=None, type=int)
@click.pass_context
def transactions(ctx, portfolio_id, limit):
    """List portfolio transactions."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if limit:
        params["limit"] = limit
    data = client.get(f"/api/portfolio/{portfolio_id}/transactions", params=params)
    output(data, ctx.obj.get("pretty", False))


@portfolio.command("holding")
@click.option("--id", "portfolio_id", required=True, help="Portfolio ID")
@click.option("--symbol", required=True, help="Ticker symbol (or symbol.TA for TASE)")
@click.option("--exchange", default="US", type=click.Choice(EXCHANGES, case_sensitive=False), help="US (default) or TASE")
@click.pass_context
def holding(ctx, portfolio_id, symbol, exchange):
    """Get details for a specific holding."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/portfolio/{portfolio_id}/holding/{apply_exchange_suffix(symbol, exchange)}")
    output(data, ctx.obj.get("pretty", False))
