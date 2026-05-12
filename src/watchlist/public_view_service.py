"""
Public View service — fetches Reddit + X chatter for a symbol via Nimble agents,
synthesizes a takeaway summary with Gemini, and caches the result globally.
"""

import json
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

REDDIT_AGENT_ID = os.getenv(
    "NIMBLE_REDDIT_AGENT_ID", "reddit_thread_search_2026_04_20_5y2qc6yy"
)
X_AGENT_ID = os.getenv(
    "NIMBLE_X_AGENT_ID", "twitter_search_recent_83bb85e3"
)
# Param key each agent expects. Both default to "query"; override per-agent if needed.
REDDIT_PARAM_KEY = os.getenv("NIMBLE_REDDIT_PARAM_KEY", "search_query")
X_PARAM_KEY = os.getenv("NIMBLE_X_PARAM_KEY", "query")

PUBLIC_VIEW_MODEL = os.getenv("PUBLIC_VIEW_MODEL", "gemini-2.5-flash")

MAX_REDDIT = 10
MAX_X = 10


def _db():
    from database import get_database_manager

    return get_database_manager()


def _nimble():
    from nimble_client import NimbleClient

    return NimbleClient()


def _normalize_reddit(raw_posts):
    """Normalize Nimble Reddit agent output into a stable shape."""
    out = []
    for p in raw_posts or []:
        if not isinstance(p, dict):
            continue
        out.append(
            {
                "title": p.get("title") or p.get("post_title") or "",
                "url": (
                    p.get("post_url")
                    or p.get("url")
                    or p.get("permalink")
                    or p.get("link")
                    or ""
                ),
                "score": p.get("score") or p.get("upvotes") or p.get("ups"),
                "subreddit": p.get("subreddit") or p.get("community") or "",
                "created_at": (
                    p.get("created_at")
                    or p.get("created_utc")
                    or p.get("date_posted")
                    or p.get("date")
                ),
                "snippet": (p.get("selftext") or p.get("body") or p.get("snippet") or "")[:400],
            }
        )
        if len(out) >= MAX_REDDIT:
            break
    return out


def _normalize_x(raw_posts):
    """Normalize Nimble X / Twitter agent output.

    Nimble's twitter agent returns items shaped like
    {"entryId": "...", "tweet": {"full_text": "...", "url": "...", ...}}
    so we unwrap the nested `tweet` object when present.
    """
    out = []
    for p in raw_posts or []:
        if not isinstance(p, dict):
            continue
        inner = p.get("tweet") if isinstance(p.get("tweet"), dict) else p
        author = ""
        # Author can be nested under tweet.core.user_results.result.legacy.screen_name
        user_legacy = (
            inner.get("core", {})
            .get("user_results", {})
            .get("result", {})
            .get("legacy", {})
            if isinstance(inner.get("core"), dict) else {}
        )
        author = (
            inner.get("author")
            or inner.get("username")
            or inner.get("user")
            or user_legacy.get("screen_name")
            or ""
        )
        text = (
            inner.get("full_text")
            or inner.get("text")
            or inner.get("content")
            or ""
        )
        likes = (
            inner.get("favorite_count")
            or inner.get("likes")
            or (inner.get("legacy") or {}).get("favorite_count")
        )
        out.append(
            {
                "author": author,
                "text": (text or "")[:400],
                "url": inner.get("url") or inner.get("link") or "",
                "created_at": inner.get("created_at") or inner.get("date") or inner.get("timestamp"),
                "likes": likes,
            }
        )
        if len(out) >= MAX_X:
            break
    return out


def _synthesize_with_gemini(symbol, reddit_posts, x_posts):
    """
    Returns: (summary_md: str, themes: list[str], bullish_pct: int|None)
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage

    if not reddit_posts and not x_posts:
        return ("_No recent community chatter found._", [], None)

    reddit_blob = "\n".join(
        f"- r/{p.get('subreddit') or '?'} | {p.get('title','')} :: {p.get('snippet','')[:200]}"
        for p in reddit_posts[:MAX_REDDIT]
    )
    x_blob = "\n".join(
        f"- @{p.get('author','?')}: {p.get('text','')[:240]}"
        for p in x_posts[:MAX_X]
    )

    prompt = (
        f"You are summarizing public retail sentiment for ${symbol}.\n"
        f"Output ONLY the three sections below, in this exact format, with the literal "
        f"'=== HEADER ===' markers. No preamble, no closing remarks.\n\n"
        f"=== SUMMARY ===\n"
        f"- bullet takeaway one\n"
        f"- bullet takeaway two\n"
        f"- bullet takeaway three\n"
        f"(3-5 bullets total, each one line, plain text)\n\n"
        f"=== BULLISH_PCT ===\n"
        f"<single integer 0-100, just the number, nothing else>\n\n"
        f"=== THEMES ===\n"
        f"<up to 3 short theme labels, comma-separated, e.g. short squeeze, Q3 earnings, AI hype>\n\n"
        f"REDDIT POSTS:\n{reddit_blob or '(none)'}\n\n"
        f"X / TWITTER POSTS:\n{x_blob or '(none)'}\n"
    )

    try:
        # gemini-2.5-flash uses ~200 reasoning tokens before producing output,
        # so we give a generous cap to avoid mid-sentence truncation.
        llm = ChatGoogleGenerativeAI(
            model=PUBLIC_VIEW_MODEL, temperature=0.2, max_output_tokens=4096
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = (resp.content or "").strip()

        def _section(label: str) -> str:
            m = re.search(
                rf"===\s*{label}\s*===\s*(.*?)(?:===|\Z)",
                raw,
                re.DOTALL | re.IGNORECASE,
            )
            return m.group(1).strip() if m else ""

        summary_md = _section("SUMMARY")
        bullish_raw = _section("BULLISH_PCT")
        themes_raw = _section("THEMES")

        bullish_pct = None
        m = re.search(r"\b(\d{1,3})\b", bullish_raw)
        if m:
            bullish_pct = max(0, min(100, int(m.group(1))))

        themes = []
        if themes_raw:
            themes = [t.strip(" -•").strip() for t in themes_raw.split(",")]
            themes = [t[:60] for t in themes if t][:3]

        if not summary_md:
            # Fallback to whole raw text if model ignored markers
            summary_md = raw[:2000]

        return (summary_md, themes, bullish_pct)
    except Exception as e:
        logger.warning("Public view synthesis failed for %s: %s", symbol, e)
        return (f"_Could not summarize community chatter ({e})._", [], None)


def is_fresh(symbol: str, ttl_hours: int = 24) -> bool:
    """True if a 'ready' row exists and is newer than ttl_hours."""
    row = _db().get_ticker_public_view(symbol)
    if not row or row.get("status") != "ready":
        return False
    last = row.get("last_updated")
    if not last:
        return False
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last) < timedelta(hours=ttl_hours)


def refresh_public_view(symbol: str) -> dict:
    """Fetch Reddit + X chatter, synthesize, and store. Never raises."""
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {"status": "error", "error_message": "empty symbol"}

    db = _db()

    # Mark computing
    try:
        db.upsert_ticker_public_view(symbol, status="computing")
    except Exception:
        logger.exception("public_view: failed to mark computing for %s", symbol)

    try:
        nimble = _nimble()
    except Exception as e:
        logger.warning("public_view: nimble unavailable: %s", e)
        db.upsert_ticker_public_view(
            symbol, status="error", error_message=f"Nimble not configured: {e}"
        )
        return {"status": "error", "error_message": str(e)}

    try:
        reddit_raw = nimble.run_agent(REDDIT_AGENT_ID, {REDDIT_PARAM_KEY: symbol})
    except Exception as e:
        logger.warning("public_view: reddit agent failed for %s: %s", symbol, e)
        reddit_raw = []

    try:
        x_raw = nimble.run_agent(X_AGENT_ID, {X_PARAM_KEY: f"${symbol}"})
    except Exception as e:
        logger.warning("public_view: x agent failed for %s: %s", symbol, e)
        x_raw = []

    reddit_posts = _normalize_reddit(reddit_raw)
    x_posts = _normalize_x(x_raw)

    if not reddit_posts and not x_posts:
        db.upsert_ticker_public_view(
            symbol,
            reddit_posts=[],
            x_posts=[],
            summary_md="_No recent community chatter found._",
            status="ready",
        )
        return {"status": "ready", "reddit": 0, "x": 0}

    summary_md, themes, bullish_pct = _synthesize_with_gemini(
        symbol, reddit_posts, x_posts
    )

    try:
        db.upsert_ticker_public_view(
            symbol,
            summary_md=summary_md,
            bullish_pct=bullish_pct,
            top_themes=themes,
            reddit_posts=reddit_posts,
            x_posts=x_posts,
            status="ready",
        )
    except Exception as e:
        logger.exception("public_view: db upsert failed for %s", symbol)
        return {"status": "error", "error_message": str(e)}

    return {
        "status": "ready",
        "reddit": len(reddit_posts),
        "x": len(x_posts),
        "bullish_pct": bullish_pct,
    }
