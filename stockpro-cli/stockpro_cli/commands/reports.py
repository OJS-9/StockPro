"""Research report commands."""

import click
from stockpro_cli.client import get_client
from stockpro_cli.output import output


@click.group()
def reports():
    """Manage research reports."""
    pass


@reports.command("list")
@click.option("--ticker", default=None, help="Filter by ticker")
@click.option("--trade-type", default=None, help="Filter by trade type")
@click.option("--sort", default=None, help="Sort field")
@click.option("--page", default=None, type=int)
@click.pass_context
def list_reports(ctx, ticker, trade_type, sort, page):
    """List research reports."""
    client = get_client(ctx.obj.get("api_url"))
    params = {}
    if ticker:
        params["ticker"] = ticker
    if trade_type:
        params["trade_type"] = trade_type
    if sort:
        params["sort"] = sort
    if page:
        params["page"] = page
    data = client.get("/api/reports", params=params)
    output(data, ctx.obj.get("pretty", False))


@reports.command("get")
@click.option("--id", "report_id", required=True, help="Report ID")
@click.pass_context
def get_report(ctx, report_id):
    """Get a single report."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/report/{report_id}")
    output(data, ctx.obj.get("pretty", False))


@reports.command("sections")
@click.option("--id", "report_id", required=True, help="Report ID")
@click.pass_context
def sections(ctx, report_id):
    """Get report sections."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/report/{report_id}/sections")
    output(data, ctx.obj.get("pretty", False))


@reports.command("delete")
@click.option("--id", "report_id", required=True, help="Report ID")
@click.pass_context
def delete_report(ctx, report_id):
    """Delete a report."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.delete(f"/api/reports/{report_id}")
    output(data, ctx.obj.get("pretty", False))


@reports.command("delete-all")
@click.option("--confirm", is_flag=True, required=True, help="Confirm deletion")
@click.pass_context
def delete_all(ctx, confirm):
    """Delete all reports. Requires --confirm."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.delete("/api/reports/all")
    output(data, ctx.obj.get("pretty", False))
