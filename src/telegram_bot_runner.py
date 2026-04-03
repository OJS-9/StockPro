"""
Telegram bot runner for StockPro.

Commands:
- /connect <token>
- /research <ticker> [trade_type]
"""

import logging
from typing import Tuple

from database import get_database_manager
from orchestrator_graph import create_session
from telegram_service import get_telegram_bot_token

logger = logging.getLogger(__name__)


def parse_research_args(args) -> Tuple[str, str]:
    ticker = (args[0] if args else "").strip().upper()
    trade_type = (" ".join(args[1:]) if len(args) > 1 else "Investment").strip()
    if not trade_type:
        trade_type = "Investment"
    return ticker, trade_type


def summarize_report_text(text: str, max_len: int = 1400) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "No report content was generated."
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


async def start_cmd(update, context):
    await update.message.reply_text(
        "StockPro bot is live.\n"
        "Use /connect <token> to link your account.\n"
        "Use /research <ticker> [trade_type] to run research."
    )


async def connect_cmd(update, context):
    token = (context.args[0] if context.args else "").strip()
    if not token:
        await update.message.reply_text("Usage: /connect <token>")
        return

    db = get_database_manager()
    user_id = db.consume_telegram_connect_token(token, str(update.effective_chat.id))
    if not user_id:
        await update.message.reply_text(
            "Invalid or expired token. Generate a new one in StockPro."
        )
        return

    await update.message.reply_text(
        "Connected successfully. You will receive alerts here."
    )


async def research_cmd(update, context):
    ticker, trade_type = parse_research_args(context.args)
    if not ticker:
        await update.message.reply_text("Usage: /research <ticker> [trade_type]")
        return

    await update.message.reply_text(
        f"Running research for {ticker} ({trade_type}). This may take a moment..."
    )

    try:
        agent = create_session()
        agent.start_research(ticker, trade_type)
        report_text = agent.generate_report(context="")
        summary = summarize_report_text(report_text)
        await update.message.reply_text(
            f"Research summary for {ticker} ({trade_type}):\n\n{summary}"
        )
    except Exception as exc:
        logger.exception("Telegram /research failed")
        await update.message.reply_text(f"Research failed: {exc}")


def build_telegram_app():
    from telegram.ext import ApplicationBuilder, CommandHandler

    app = ApplicationBuilder().token(get_telegram_bot_token()).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("connect", connect_cmd))
    app.add_handler(CommandHandler("research", research_cmd))
    return app


def run_bot():
    from telegram import Update

    app = build_telegram_app()
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    run_bot()
