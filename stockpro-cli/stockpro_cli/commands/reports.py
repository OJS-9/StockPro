"""Research report commands."""

import time
import click
from stockpro_cli.client import get_client
from stockpro_cli.output import output


@click.group()
def reports():
    """Manage research reports."""
    pass


def _prompt_questions(questions):
    """Interactively prompt for each question and return a list of answers."""
    answers = []
    for q in questions:
        q_text = q.get("question") if isinstance(q, dict) else str(q)
        opts = q.get("options", []) if isinstance(q, dict) else []
        click.echo(f"\n{q_text}")
        if opts:
            for i, opt in enumerate(opts, 1):
                click.echo(f"  {i}. {opt}")
            choice = click.prompt("Your choice", type=click.IntRange(1, len(opts)))
            answers.append(opts[choice - 1])
        else:
            answers.append(click.prompt("Your answer", default="", show_default=False))
    return answers


def _prompt_subjects(subjects):
    """Show research subjects and return selected ids (None = use defaults)."""
    if not subjects:
        return None
    ordered = sorted(subjects, key=lambda s: s.get("priority", 99))
    click.echo("\nResearch areas to cover (sorted by relevance):")
    for i, s in enumerate(ordered, 1):
        name = s.get("name", s.get("id", "?"))
        desc = s.get("description", "")
        click.echo(f"  {i:>2}. {name} — {desc}")
    click.echo(
        "\nEnter numbers separated by commas (e.g. 1,3,5), "
        "or press Enter to use the recommended defaults."
    )
    raw = click.prompt("Your selection", default="", show_default=False)
    raw = (raw or "").strip()
    if not raw:
        return None
    ids = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            idx = int(token)
            if 1 <= idx <= len(ordered):
                ids.append(ordered[idx - 1]["id"])
        except ValueError:
            continue
    return ids or None


@reports.command("generate")
@click.option("--ticker", required=True, help="Stock ticker symbol (e.g. AAPL)")
@click.option(
    "--trade-type",
    required=True,
    type=click.Choice(["Investment", "Swing Trade", "Day Trade"], case_sensitive=False),
    help="Type of trade to research",
)
@click.option("--context", default="", help="Optional research context or notes")
@click.option(
    "--no-questions",
    is_flag=True,
    default=False,
    help="Skip clarifying questions (non-interactive mode)",
)
@click.option(
    "--poll-interval",
    default=5,
    show_default=True,
    type=int,
    help="Seconds between status polls",
)
@click.pass_context
def generate(ctx, ticker, trade_type, context, no_questions, poll_interval):
    """Generate a new research report. Polls until complete."""
    client = get_client(ctx.obj.get("api_url"))
    pretty = ctx.obj.get("pretty", False)

    # Kick off generation
    resp = client.post(
        "/api/reports/generate",
        data={
            "ticker": ticker,
            "trade_type": trade_type,
            "context": context,
            "no_questions": no_questions,
        },
    )
    if not resp.get("success"):
        output(resp, pretty)
        return

    session_id = resp.get("session_id")
    if not session_id:
        output({"error": "No session_id returned from server"}, pretty)
        return

    # Clarifying questions are mandatory — the flow matches the web app.
    # Callers who want to skip must pass --no-questions explicitly.
    questions = resp.get("questions") or []
    subjects = resp.get("subjects") or []
    if questions and not no_questions:
        if not pretty:
            output(
                {
                    "error": "clarifying_questions_required",
                    "message": (
                        "Report generation requires answering clarifying questions. "
                        "Re-run with --pretty to answer interactively, or pass "
                        "--no-questions to skip (not recommended)."
                    ),
                    "session_id": session_id,
                    "questions": questions,
                    "subjects": subjects,
                },
                pretty,
            )
            raise SystemExit(2)

        click.echo("\nA few quick questions to tailor your report:")
        answers = _prompt_questions(questions)
        selected_subject_ids = _prompt_subjects(subjects)

        payload = {"session_id": session_id, "answers": answers}
        if selected_subject_ids:
            payload["selected_subject_ids"] = selected_subject_ids
        answer_resp = client.post("/api/reports/answer", data=payload)
        if not answer_resp.get("success"):
            output(answer_resp, pretty)
            return

    if pretty:
        click.echo(f"\nGenerating report for {ticker} ({trade_type})...")

    # Poll until ready or error
    last_step = ""
    while True:
        status = client.get(f"/api/report_status/{session_id}")
        state = status.get("status", "unknown")
        step = status.get("step", "")
        progress = status.get("progress", 0)

        if pretty and step and step != last_step:
            click.echo(f"  [{progress:>3}%] {step}")
            last_step = step

        if state == "ready":
            report_id = status.get("report_id")
            if pretty:
                click.echo(f"\nDone! Report ID: {report_id}")
            else:
                output({"status": "ready", "report_id": report_id}, pretty)
            return

        if state == "error":
            msg = status.get("message", "Unknown error")
            if pretty:
                click.echo(f"\nError: {msg}", err=True)
            else:
                output({"status": "error", "message": msg}, pretty)
            raise SystemExit(1)

        time.sleep(poll_interval)


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
