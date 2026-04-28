"""Price alert commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.exchanges import EXCHANGES, apply_exchange_suffix
from stockpro_cli.output import output


@click.group()
def alerts():
    """Manage price alerts."""
    pass


@alerts.command("list")
@click.pass_context
def list_alerts(ctx):
    """List all alerts."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/alerts")
    output(data, ctx.obj.get("pretty", False))


@alerts.command("create")
@click.option("--symbol", required=True, help="Ticker symbol (or symbol.TA for TASE)")
@click.option("--exchange", default="US", type=click.Choice(EXCHANGES, case_sensitive=False), help="US (default) or TASE. TASE target prices must be in ILS.")
@click.option("--direction", required=True, type=click.Choice(["above", "below"]))
@click.option("--target-price", required=True, type=float)
@click.option("--asset-type", default=None, help="stock or crypto")
@click.pass_context
def create_alert(ctx, symbol, exchange, direction, target_price, asset_type):
    """Create a new price alert."""
    client = get_client(ctx.obj.get("api_url"))
    payload = {
        "symbol": apply_exchange_suffix(symbol, exchange),
        "direction": direction,
        "target_price": target_price,
    }
    if asset_type:
        payload["asset_type"] = asset_type
    data = client.post("/api/alerts", payload)
    output(data, ctx.obj.get("pretty", False))


@alerts.command("delete")
@click.option("--id", "alert_id", required=True, help="Alert ID")
@click.pass_context
def delete_alert(ctx, alert_id):
    """Delete an alert."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.delete(f"/api/alerts/{alert_id}")
    output(data, ctx.obj.get("pretty", False))


@alerts.command("pause")
@click.option("--id", "alert_id", required=True, help="Alert ID")
@click.pass_context
def pause_alert(ctx, alert_id):
    """Pause an alert."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.patch(f"/api/alerts/{alert_id}", {"active": False})
    output(data, ctx.obj.get("pretty", False))


@alerts.command("resume")
@click.option("--id", "alert_id", required=True, help="Alert ID")
@click.pass_context
def resume_alert(ctx, alert_id):
    """Resume a paused alert."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.patch(f"/api/alerts/{alert_id}", {"active": True})
    output(data, ctx.obj.get("pretty", False))


@alerts.command("notifications")
@click.option("--limit", default=None, type=int)
@click.pass_context
def notifications(ctx, limit):
    """List alert notifications."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if limit:
        params["limit"] = limit
    data = client.get("/api/alerts/notifications", params=params)
    output(data, ctx.obj.get("pretty", False))


@alerts.command("mark-read")
@click.option("--id", "notification_id", default=None, help="Notification ID (omit to mark all)")
@click.pass_context
def mark_read(ctx, notification_id):
    """Mark notifications as read."""
    client = get_client(ctx.obj.get("api_url"))
    if notification_id:
        data = client.patch(f"/api/alerts/notifications/{notification_id}", {"read": True})
    else:
        data = client.post("/api/alerts/notifications/mark-all-read")
    output(data, ctx.obj.get("pretty", False))
