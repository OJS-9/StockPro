"""
Telegram helper utilities for StockPro notifications and bot responses.
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


def get_telegram_bot_token() -> str:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


async def send_telegram_text(chat_id: str, text: str) -> None:
    from telegram import Bot

    bot = Bot(token=get_telegram_bot_token())
    await bot.send_message(chat_id=chat_id, text=text)


def send_telegram_text_sync(chat_id: str, text: str) -> None:
    """Sync wrapper usable from existing sync alert evaluation flows."""
    try:
        asyncio.run(send_telegram_text(chat_id, text))
    except RuntimeError:
        # Fallback for contexts with an already-running event loop.
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(send_telegram_text(chat_id, text))
        finally:
            loop.close()
