"""StockPro CLI entry point."""

import json
import sys
import click
from stockpro_cli.auth import auth
from stockpro_cli.client import get_client
from stockpro_cli.output import output
from stockpro_cli.commands.portfolio import portfolio
from stockpro_cli.commands.alerts import alerts
from stockpro_cli.commands.reports import reports
from stockpro_cli.commands.watchlist import watchlist
from stockpro_cli.commands.ticker import ticker
from stockpro_cli.commands.telegram import telegram
from stockpro_cli.commands.settings import settings
from stockpro_cli.commands.home import home
from stockpro_cli.commands.news import news


@click.group()
@click.option("--pretty", is_flag=True, help="Human-readable output instead of JSON")
@click.option("--api-url", default=None, help="Override API URL")
@click.version_option(package_name="stockpro-cli")
@click.pass_context
def cli(ctx, pretty, api_url):
    """StockPro CLI -- AI-powered stock research from your terminal."""
    ctx.ensure_object(dict)
    ctx.obj["pretty"] = pretty
    if api_url:
        ctx.obj["api_url"] = api_url


# Register command groups
cli.add_command(auth)
cli.add_command(portfolio)
cli.add_command(alerts)
cli.add_command(reports)
cli.add_command(watchlist)
cli.add_command(ticker)
cli.add_command(telegram)
cli.add_command(settings)

# Register standalone commands
cli.add_command(home)
cli.add_command(news)


@cli.command()
@click.pass_context
def usage(ctx):
    """Get API usage stats."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get("/api/usage")
    output(data, ctx.obj.get("pretty", False))


@cli.command("position-check")
@click.option("--ticker", "symbol", required=True, help="Ticker symbol")
@click.pass_context
def position_check(ctx, symbol):
    """Check your position in a ticker."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/position_check/{symbol.upper()}")
    output(data, ctx.obj.get("pretty", False))


@cli.command("report-status")
@click.option("--session-id", required=True, help="Research session ID")
@click.pass_context
def report_status(ctx, session_id):
    """Check status of a research report generation."""
    client = get_client(ctx.obj.get("api_url"))
    data = client.get(f"/api/report_status/{session_id}")
    output(data, ctx.obj.get("pretty", False))


@cli.command("delete-account")
@click.option("--confirm", is_flag=True, required=True, help="Confirm account deletion")
@click.option(
    "--yes-i-mean-it",
    is_flag=True,
    default=False,
    help="Required to proceed without an interactive TTY (machine mode).",
)
@click.pass_context
def delete_account(ctx, confirm, yes_i_mean_it):
    """Delete your account. Destructive — requires double confirmation."""
    if sys.stdin.isatty():
        typed = click.prompt(
            'This will permanently delete your account. Type "DELETE" to confirm',
            default="",
            show_default=False,
        )
        if typed.strip() != "DELETE":
            click.echo("Aborted.", err=True)
            raise SystemExit(1)
    else:
        if not yes_i_mean_it:
            click.echo(
                json.dumps(
                    {"error": "non-interactive delete-account requires --yes-i-mean-it"}
                ),
                err=True,
            )
            sys.exit(2)

    client = get_client(ctx.obj.get("api_url"))
    data = client.delete("/api/account")
    output(data, ctx.obj.get("pretty", False))


def main():
    """Entry point with a top-level error handler so users never see a raw traceback."""
    try:
        cli(standalone_mode=True)
    except SystemExit:
        raise
    except KeyboardInterrupt:
        click.echo(json.dumps({"error": "interrupted"}), err=True)
        sys.exit(130)
    except Exception as exc:
        click.echo(
            json.dumps(
                {"error": "unexpected_error", "type": type(exc).__name__, "detail": str(exc)}
            ),
            err=True,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
