"""
Flask web interface for the Stock Research AI Agent.
"""

import sys
from pathlib import Path

# Add project root to Python path to allow imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
    Response,
    abort,
)
from flask_wtf.csrf import CSRFProtect
from clerk_backend_api import Clerk as ClerkClient, AuthenticateRequestOptions
import os
import re
import threading
import queue
import json
import time
import requests
from functools import wraps
from dotenv import load_dotenv
import uuid
import bleach
import markdown as md_lib
from markupsafe import Markup
from decimal import Decimal
from datetime import datetime, timedelta
from psycopg2.extras import RealDictCursor

from orchestrator_graph import OrchestratorSession, create_session
from langsmith_service import create_emitter
from portfolio.portfolio_service import get_portfolio_service
from portfolio.history_service import get_history_service
from watchlist.watchlist_service import get_watchlist_service
from data_providers import DataProviderFactory
from report_storage import ReportStorage
from pdf_generator import get_pdf_generator

# Load environment variables
load_dotenv()

# Clerk auth client
_clerk_secret_key_raw = os.getenv("CLERK_SECRET_KEY")
if not _clerk_secret_key_raw:
    raise RuntimeError("CLERK_SECRET_KEY environment variable is not set")
_clerk_jwt_key_raw = os.getenv("CLERK_JWT_KEY")
if not _clerk_jwt_key_raw:
    raise RuntimeError("CLERK_JWT_KEY environment variable is not set")
clerk_client = ClerkClient(bearer_auth=_clerk_secret_key_raw)
CLERK_JWT_KEY = _clerk_jwt_key_raw.replace("\\n", "\n")

# Create Flask app
# Set template and static folders explicitly to point to project root
app = Flask(
    __name__,
    template_folder=str(project_root / "templates"),
    static_folder=str(project_root / "static"),
)
_secret_key = os.getenv("FLASK_SECRET_KEY")
if not _secret_key:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set")
app.secret_key = _secret_key
csrf = CSRFProtect(app)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    get_remote_address, app=app, default_limits=[], storage_uri="memory://"
)


@limiter.request_filter
def _skip_rate_limits_in_tests():
    """Pytest sets TESTING=True; avoid 429s on routes under tight limits."""
    from flask import current_app

    return bool(current_app.config.get("TESTING"))


# Tunable via env for staging/production (defaults match Phase 1 roadmap abuse protection)
def _research_rate_limit():
    return os.getenv("STOCKPRO_RATE_LIMIT_RESEARCH", "30 per hour")


def _report_gen_rate_limit():
    return os.getenv("STOCKPRO_RATE_LIMIT_REPORT_GEN", "15 per hour")


def _report_post_rate_limit():
    return os.getenv("STOCKPRO_RATE_LIMIT_GENERATE_REPORT", "20 per hour")


def _popup_start_rate_limit():
    return os.getenv("STOCKPRO_RATE_LIMIT_POPUP_START", "60 per hour")


def _continue_conversation_rate_limit():
    """Limit POST /continue (chat agent turns + SSE) — same abuse class as research."""
    return os.getenv("STOCKPRO_RATE_LIMIT_CONTINUE", "60 per hour")


def _chat_report_rate_limit():
    """Limit POST /chat_report (Q&A against stored report)."""
    return os.getenv("STOCKPRO_RATE_LIMIT_CHAT_REPORT", "40 per hour")


def sse_user_facing_error(exc: BaseException) -> str:
    """Build a short SSE error string for the chat UI (no stack traces; cap API noise)."""
    msg = (str(exc) or "").strip()
    if not msg:
        return "Something went wrong. Please try again."
    max_len = 500
    if len(msg) > max_len:
        return msg[: max_len - 3] + "..."
    return msg


def flash_status(message: str, status_type: str = "info"):
    """Set a status message and type in the session for the next page render.
    status_type: 'success', 'error', or 'info'
    """
    session["status_message"] = message
    session["status_type"] = status_type


def pop_status():
    """Pop status_message and status_type from the session, returning a dict."""
    return {
        "status_message": session.pop("status_message", None),
        "status_type": session.pop("status_type", "info"),
    }


def _free_tier_quota_message() -> str:
    from report_usage import get_free_tier_report_limit

    limit = get_free_tier_report_limit()
    if limit == 3:
        return "You've used your 3 free reports this month."
    return f"You've used your {limit} free reports this month."


def _session_hits_report_quota() -> bool:
    uid = session.get("user_id")
    if not uid:
        return False
    from database import get_database_manager
    from report_usage import quota_exceeded_for_user

    db = get_database_manager()
    exceeded, _, _ = quota_exceeded_for_user(db, uid)
    return exceeded


def _report_quota_json_error():
    return jsonify(
        {"error": "limit_reached", "message": _free_tier_quota_message()}
    ), 403


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" in session:
            return f(*args, **kwargs)
        # Verify Clerk session token via authenticate_request
        request_state = clerk_client.authenticate_request(
            request, AuthenticateRequestOptions(jwt_key=CLERK_JWT_KEY)
        )
        if request_state.is_authenticated:
            clerk_user_id = request_state.payload["sub"]
            if "user_id" not in session or session["user_id"] != clerk_user_id:
                # Upsert user in PostgreSQL (Supabase-compatible)
                from database import get_database_manager

                db = get_database_manager()
                user = db.get_user_by_id(clerk_user_id)
                if not user:
                    clerk_user = clerk_client.users.get(user_id=clerk_user_id)
                    email = ""
                    username = clerk_user_id
                    if clerk_user.email_addresses:
                        email = clerk_user.email_addresses[0].email_address or ""
                    if clerk_user.username:
                        username = clerk_user.username
                    elif clerk_user.first_name or clerk_user.last_name:
                        username = (
                            f"{clerk_user.first_name or ''}{clerk_user.last_name or ''}".strip()
                            or clerk_user_id
                        )
                    db.create_user(
                        user_id=clerk_user_id, username=username, email=email
                    )
                else:
                    username = user.get("username", clerk_user_id)
                session["user_id"] = clerk_user_id
                session["username"] = username
                # Warm price cache in background — fire and forget
                threading.Thread(
                    target=_warm_portfolio_cache, args=(clerk_user_id,), daemon=True
                ).start()
                get_or_create_session_id()
            return f(*args, **kwargs)
        app.logger.warning("Clerk auth failed: %s", request_state.reason)
        return redirect(url_for("sign_in"))

    return decorated


@app.context_processor
def inject_user():
    return {
        "current_user": {
            "is_authenticated": "user_id" in session,
            "user_id": session.get("user_id"),
            "username": session.get("username"),
        },
        "clerk_publishable_key": os.getenv("CLERK_PUBLISHABLE_KEY", ""),
    }


_MD_ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "pre",
    "code",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "hr",
    "br",
    "ul",
    "ol",
    "li",
]
_MD_ALLOWED_ATTRS = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, "*": ["class"]}


@app.template_filter("currency")
def currency_filter(value):
    try:
        return "{:,.2f}".format(float(value))
    except (ValueError, TypeError):
        return "0.00"


@app.template_filter("markdown")
def markdown_filter(text):
    raw_html = md_lib.markdown(
        text or "", extensions=["tables", "fenced_code", "nl2br", "sane_lists"]
    )
    return Markup(
        bleach.clean(
            raw_html, tags=_MD_ALLOWED_TAGS, attributes=_MD_ALLOWED_ATTRS, strip=True
        )
    )


@app.template_filter("markdown_preview")
def markdown_preview_filter(text, length=250):
    if not text:
        return ""
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,2}([^*\n]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_([^_\n]+)_", r"\1", text)
    text = re.sub(r"`[^`\n]+`", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"^[-*+]\s+", "", text, flags=re.MULTILINE)
    text = " ".join(text.split())
    return text[:length] + ("..." if len(text) > length else "")


def _page_range(current, total, delta=2):
    pages = sorted(
        {1, total}
        | set(range(max(1, current - delta), min(total, current + delta) + 1))
    )
    result, prev = [], None
    for p in pages:
        if prev and p - prev > 1:
            result.append(None)  # None = ellipsis
        result.append(p)
        prev = p
    return result


# Global agent instances (keyed by session ID)
agent_sessions = {}

# SSE step queues — keyed by session_id; cleaned up after stream completes
_sse_queues: dict = {}

# Background generation status — keyed by session_id
_generation_status: dict = {}

# Session creation timestamps for TTL eviction
_session_created_at: dict = {}


def _evict_stale_sessions(max_age_seconds: int = 86400):
    cutoff = time.time() - max_age_seconds
    stale = [sid for sid, t in _session_created_at.items() if t < cutoff]
    for sid in stale:
        agent_sessions.pop(sid, None)
        _generation_status.pop(sid, None)
        _sse_queues.pop(sid, None)
        _session_created_at.pop(sid, None)


def initialize_session(session_id: str) -> OrchestratorSession:
    """Initialize or get orchestrator session."""
    if session_id not in agent_sessions:
        _evict_stale_sessions()
        _session_created_at[session_id] = time.time()
        try:
            agent_sessions[session_id] = create_session()
        except Exception as e:
            raise ValueError(f"Failed to initialize session: {str(e)}")
    return agent_sessions[session_id]


def get_or_create_session_id():
    """Get or create a session ID for the current user."""
    if "session_id" not in session:
        session["session_id"] = str(uuid.uuid4())
    return session["session_id"]


def _warm_portfolio_cache(user_id):
    """Background warm: pre-fetch prices for portfolio + watchlist into price_cache."""
    try:
        svc = get_portfolio_service()

        # 1. Collect portfolio symbols
        stock_symbols, crypto_symbols = set(), set()
        for p in svc.list_portfolios(user_id):
            for h in svc.db.get_holdings(p["portfolio_id"]):
                if Decimal(str(h.get("total_quantity", 0))) > 0:
                    if h["asset_type"] == "crypto":
                        crypto_symbols.add(h["symbol"])
                    else:
                        stock_symbols.add(h["symbol"])

        # 2. Also collect watchlist symbols for this user (deduplicated into same sets)
        for row in svc.db.get_watched_symbols_for_user(user_id):
            if row["asset_type"] == "crypto":
                crypto_symbols.add(row["symbol"])
            else:
                stock_symbols.add(row["symbol"])

        # 3. Check DB for already-fresh entries (15-min TTL) — skip those
        all_symbols = list(stock_symbols | crypto_symbols)
        cached = svc.db.get_cached_prices(all_symbols)
        now = datetime.now()

        def _is_fresh(sym):
            row = cached.get(sym)
            if not row or not row.get("last_updated"):
                return False
            return (now - row["last_updated"]) < timedelta(minutes=15)

        stale_stocks = [s for s in stock_symbols if not _is_fresh(s)]
        stale_cryptos = [s for s in crypto_symbols if not _is_fresh(s)]

        # 4. Fetch only stale symbols
        if stale_stocks:
            stock_provider = DataProviderFactory.get_provider("stock")
            prices = stock_provider.get_prices_batch_warmup(stale_stocks)
            for sym, data in prices.items():
                svc.db.upsert_price_cache(
                    sym, "stock", float(data["price"]), data.get("change_percent"), None
                )

        if stale_cryptos:
            crypto_provider = DataProviderFactory.get_provider("crypto")
            prices = crypto_provider.get_prices_batch(stale_cryptos)
            for sym, price in prices.items():
                svc.db.upsert_price_cache(sym, "crypto", float(price), None, None)

    except Exception:
        pass  # Never surface errors into login flow


def _fetch_clarifying_questions(ticker: str, trade_type: str) -> list:
    """Make a single LLM call to get 1-3 multiple-choice clarifying questions."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage

    prompt = (
        f"You are a stock research assistant. A user wants a {trade_type} research report on {ticker}. "
        "Generate 1–3 multiple-choice clarifying questions to better tailor the report. "
        "Each question must have 3–4 short answer options. "
        "Return ONLY a JSON array of objects with keys 'question' (string) and 'options' (array of strings). "
        'Example: [{"question": "What is your time horizon?", "options": ["Under 1 month", "1–6 months", "6–12 months", "1+ years"]}]'
    )
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", temperature=0.3, max_output_tokens=400
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content or ""
        # Strip markdown fences if present
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        questions = json.loads(raw.strip())
        if isinstance(questions, list) and questions and isinstance(questions[0], dict):
            return questions
    except Exception:
        pass
    return [
        {
            "question": f"What is your primary goal for researching {ticker}?",
            "options": [
                "Long-term investment",
                "Swing trade",
                "Day trade",
                "General analysis",
            ],
        }
    ]


# ==================== Auth Routes ====================


def _safe_redirect_url(next_url, fallback="/"):
    """Allow only relative paths to prevent open redirects."""
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return fallback


@app.route("/sign-in")
def sign_in():
    """Sign-in page (Clerk hosted component)."""
    if "user_id" in session:
        return redirect(url_for("index"))
    next_url = request.args.get("next", "")
    return render_template("sign_in.html", next_url=_safe_redirect_url(next_url, "/"))


@app.route("/auth/sso-callback")
def auth_sso_callback():
    """OAuth/SSO callback: ClerkJS runs handleRedirectCallback here to set __session cookie, then redirects."""
    next_url = request.args.get("next", "")
    redirect_url = _safe_redirect_url(next_url, "/")
    return render_template("auth_sso_callback.html", redirect_url=redirect_url)


@app.route("/sign-up")
def sign_up():
    """Sign-up page (Clerk hosted component)."""
    if "user_id" in session:
        return redirect(url_for("index"))
    return render_template("sign_up.html")


@app.route("/sign-out")
def sign_out():
    """Sign out: clear Flask session and redirect to sign-in."""
    session.clear()
    return redirect(url_for("sign_in"))


# --- Waitlist (ConvertKit) ---

_WAITLIST_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)


def _subscribe_waitlist_convertkit(email: str) -> None:
    """Send email to ConvertKit when configured; otherwise log only. Logs API failures."""
    api_key = (os.getenv("CONVERTKIT_API_KEY") or "").strip()
    form_id = (os.getenv("CONVERTKIT_FORM_ID") or "").strip()
    if not api_key or not form_id:
        app.logger.info("Waitlist signup (ConvertKit disabled): %s", email)
        return
    url = f"https://api.convertkit.com/v3/forms/{form_id}/subscribe"
    try:
        resp = requests.post(
            url,
            json={"api_key": api_key, "email": email},
            timeout=15,
        )
        if resp.status_code >= 400:
            app.logger.warning(
                "ConvertKit subscribe failed: status=%s body=%s",
                resp.status_code,
                (resp.text or "")[:500],
            )
    except Exception as exc:
        app.logger.warning("ConvertKit subscribe error: %s", exc, exc_info=True)


@app.route("/waitlist")
def waitlist():
    """Public waitlist landing page."""
    return render_template("waitlist.html", **pop_status())


@app.route("/waitlist/join", methods=["POST"])
@limiter.limit("30 per minute", key_func=get_remote_address)
def waitlist_join():
    """Accept waitlist signup; sync to ConvertKit when configured."""
    email = (request.form.get("email") or "").strip()
    if not email or not _WAITLIST_EMAIL_RE.match(email):
        flash_status("Please enter a valid email address.", "error")
        return redirect(url_for("waitlist"))
    _subscribe_waitlist_convertkit(email)
    return redirect(url_for("waitlist_thanks"))


@app.route("/waitlist/thanks")
def waitlist_thanks():
    """Thank-you page after waitlist signup."""
    return render_template("waitlist_thanks.html")


@app.route("/login")
def login():
    """Compatibility redirect for legacy /login links."""
    return redirect(url_for("sign_in"))


def _render_authenticated_home():
    """Render the current authenticated app homepage (Markets)."""
    # Initialize session ID if needed
    get_or_create_session_id()

    # Get current values from session for form pre-filling
    current_ticker = session.get("current_ticker", "")
    current_trade_type = session.get("current_trade_type", "Investment")

    # Pinned tickers for Market Overview
    pinned_tickers = None
    user_id = session.get("user_id")
    if user_id:
        try:
            watchlist_svc = get_watchlist_service()
            pinned_tickers = watchlist_svc.get_pinned_tickers(user_id)
        except Exception:
            pinned_tickers = None

    return render_template(
        "index.html",
        current_ticker=current_ticker,
        current_trade_type=current_trade_type,
        pinned_tickers=pinned_tickers,
    )


@app.route("/")
def index():
    """Unified home page at '/'.

    - Authenticated: show the existing app homepage (Markets).
    - Unauthenticated: show a public landing page with waitlist signup.
    """
    if "user_id" in session:
        return _render_authenticated_home()

    # If the user has a Clerk session cookie but no Flask session yet, hydrate
    # the session and redirect to the authenticated homepage.
    try:
        request_state = clerk_client.authenticate_request(
            request, AuthenticateRequestOptions(jwt_key=CLERK_JWT_KEY)
        )
        if request_state.is_authenticated:
            clerk_user_id = request_state.payload["sub"]
            from database import get_database_manager

            db = get_database_manager()
            user = db.get_user_by_id(clerk_user_id)
            if not user:
                clerk_user = clerk_client.users.get(user_id=clerk_user_id)
                email = ""
                username = clerk_user_id
                if clerk_user.email_addresses:
                    email = clerk_user.email_addresses[0].email_address or ""
                if clerk_user.username:
                    username = clerk_user.username
                elif clerk_user.first_name or clerk_user.last_name:
                    username = (
                        f"{clerk_user.first_name or ''}{clerk_user.last_name or ''}".strip()
                        or clerk_user_id
                    )
                db.create_user(user_id=clerk_user_id, username=username, email=email)
            else:
                username = user.get("username", clerk_user_id)

            session["user_id"] = clerk_user_id
            session["username"] = username
            threading.Thread(
                target=_warm_portfolio_cache, args=(clerk_user_id,), daemon=True
            ).start()
            get_or_create_session_id()
            return redirect(url_for("index"))
    except Exception as exc:
        app.logger.warning("Clerk auth check on '/' failed: %s", exc, exc_info=True)

    return render_template("home_public.html", **pop_status())


@app.route("/chat")
@login_required
def chat():
    """Render the chat interface."""
    # Initialize session ID if needed
    get_or_create_session_id()

    # Get conversation history from session
    conversation_history = session.get("conversation_history", [])
    current_ticker = session.get("current_ticker", "")
    current_trade_type = session.get("current_trade_type", "Investment")

    return render_template(
        "chat.html",
        conversation_history=conversation_history,
        current_ticker=current_ticker,
        current_trade_type=current_trade_type,
    )


@app.route("/start_research", methods=["POST"])
@login_required
@limiter.limit(_research_rate_limit, key_func=get_remote_address)
def start_research():
    """Handle form submission to start research."""
    ticker = request.form.get("ticker", "").strip()
    trade_type = request.form.get("trade_type", "")

    # Validate input
    if not ticker:
        flash_status("Please enter a stock ticker.", "error")
        return redirect(url_for("index"))

    if not trade_type:
        flash_status("Please select a trade type.", "error")
        return redirect(url_for("index"))

    ticker = ticker.upper()

    if _session_hits_report_quota():
        flash_status(_free_tier_quota_message(), "error")
        return redirect(url_for("index"))

    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)
        agent.reset_conversation()

        # Start research
        response = agent.start_research(ticker, trade_type)

        # Store conversation in session as list of message dicts
        conversation_history = [{"role": "assistant", "content": response}]

        session["conversation_history"] = conversation_history
        session["current_ticker"] = ticker
        session["current_trade_type"] = trade_type
        flash_status(f"Research started for {ticker} ({trade_type})", "success")

    except Exception as e:
        flash_status(f"Error: {str(e)}", "error")
        session["conversation_history"] = []

    return redirect(url_for("chat"))


@app.route("/continue", methods=["POST"])
@login_required
@limiter.limit(_continue_conversation_rate_limit, key_func=get_remote_address)
def continue_conversation():
    """Start a conversation turn in a background thread; return SSE session info."""
    user_input = request.form.get("user_response", "").strip()

    if not user_input:
        return jsonify({"success": False, "error": "⚠️ Please enter a response."}), 400

    session_id = get_or_create_session_id()
    agent = initialize_session(session_id)
    agent.user_id = session.get("user_id")
    agent.username = session.get("username")

    # Snapshot mutable session state so the background thread can read it safely
    previous_report_id = session.get("current_report_id")
    conversation_history_snapshot = list(session.get("conversation_history", []))

    # Create SSE queue and emitter
    step_q: queue.Queue = queue.Queue()
    _sse_queues[session_id] = step_q
    emitter = create_emitter(step_q)
    agent.set_emitter(emitter)

    def run_in_background():
        try:
            response = agent.continue_conversation(user_input)

            new_history = list(conversation_history_snapshot)
            new_history.append({"role": "user", "content": user_input})
            new_history.append({"role": "assistant", "content": response})

            current_report_id = agent.current_report_id
            report_generated = False
            report_preview = None

            if current_report_id and current_report_id != previous_report_id:
                report_text = getattr(agent, "last_report_text", None) or ""
                if report_text:
                    report_preview = f"# Research Report\n\n{report_text}"
                    new_history.append({"role": "assistant", "content": report_preview})
                    report_generated = True

            step_q.put(
                {
                    "type": "done",
                    "user_message": user_input,
                    "assistant_message": response,
                    "conversation_history": new_history,
                    "report_generated": report_generated,
                    "report_preview": report_preview,
                    "current_report_id": current_report_id,
                    "report_text": getattr(agent, "last_report_text", None) or "",
                }
            )
        except Exception as e:
            app.logger.exception("continue_conversation background task failed")
            step_q.put({"type": "error", "message": sse_user_facing_error(e)})
        finally:
            agent.set_emitter(None)

    t = threading.Thread(target=run_in_background, daemon=True)
    t.start()

    return jsonify({"success": True, "streaming": True, "session_id": session_id})


@app.route("/stream/<session_id>")
@login_required
def stream_steps(session_id: str):
    """SSE endpoint — streams step messages until 'done' or 'error'."""
    if session.get("session_id") != session_id:
        abort(403)

    step_q = _sse_queues.get(session_id)
    if step_q is None:
        # No active stream — send immediate done with empty payload
        def empty():
            yield 'data: {"type": "done"}\n\n'

        return Response(
            empty(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def event_stream():
        try:
            while True:
                try:
                    event = step_q.get(timeout=120)
                except queue.Empty:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out'})}\n\n"
                    return

                yield f"data: {json.dumps(event)}\n\n"

                if event.get("type") in ("done", "error"):
                    return
        finally:
            _sse_queues.pop(session_id, None)

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/commit_session", methods=["POST"])
@login_required
def commit_session():
    """Persist state from SSE 'done' payload back into the Flask session."""
    data = request.get_json(force=True) or {}
    if "conversation_history" in data:
        session["conversation_history"] = data["conversation_history"]
    if "current_report_id" in data and data["current_report_id"]:
        session["current_report_id"] = data["current_report_id"]
    if "report_text" in data and data["report_text"]:
        session["report_text"] = data["report_text"]
    return jsonify({"success": True})


@app.route("/generate_report", methods=["POST"])
@login_required
@limiter.limit(_report_post_rate_limit, key_func=get_remote_address)
def generate_report():
    """Handle form submission to generate report after followup questions."""
    if _session_hits_report_quota():
        flash_status(_free_tier_quota_message(), "error")
        return redirect(url_for("chat"))

    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)

        # Extract context from conversation history
        conversation_history = session.get("conversation_history", [])
        context = ""
        for msg in conversation_history:
            if msg.get("role") == "user":
                context += f"User: {msg.get('content', '')}\n"

        # Generate report
        flash_status("Generating report... This may take a few minutes.", "info")
        session["conversation_history"] = conversation_history  # Preserve history
        session.modified = True

        report_text = agent.generate_report(context=context)
        report_id = agent.current_report_id

        # Store report in session
        session["current_report_id"] = report_id
        session["report_text"] = report_text
        flash_status(
            f"Report generated successfully! Report ID: {report_id[:8]}...", "success"
        )

        # Add full report to conversation
        report_preview = f"# Research Report\n\n{report_text}"
        conversation_history.append({"role": "assistant", "content": report_preview})
        session["conversation_history"] = conversation_history

    except Exception as e:
        flash_status(f"Error generating report: {str(e)}", "error")

    return redirect(url_for("chat"))


@app.route("/chat_report", methods=["POST"])
@login_required
@limiter.limit(_chat_report_rate_limit, key_func=get_remote_address)
def chat_report():
    """Handle form submission to chat with report."""
    question = request.form.get("chat_question", "").strip()

    # Validate input
    if not question:
        flash_status("Please enter a question.", "info")
        return redirect(url_for("index"))

    if "current_report_id" not in session:
        flash_status("No report available. Please generate a report first.", "error")
        return redirect(url_for("index"))

    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)
        agent.current_report_id = session.get("current_report_id")

        # Get answer from chat agent
        answer = agent.chat_with_report(question)

        # Update chat history in session
        chat_history = session.get("chat_history", [])
        chat_history.append({"role": "user", "content": question})
        chat_history.append({"role": "assistant", "content": answer})
        session["chat_history"] = chat_history
        flash_status("Answer received", "success")

    except Exception as e:
        flash_status(f"Error: {str(e)}", "error")

    return redirect(url_for("index"))


@app.route("/clear", methods=["POST"])
@login_required
def clear_conversation():
    """Handle form submission to clear conversation."""
    session["conversation_history"] = []
    session["current_ticker"] = ""
    session["current_trade_type"] = "Investment"
    flash_status("Conversation cleared. Ready for new research.", "info")

    # Optionally reset agent
    session_id = get_or_create_session_id()
    if session_id in agent_sessions:
        try:
            agent_sessions[session_id].reset_conversation()
        except Exception as e:
            app.logger.warning(f"Session reset failed: {e}")

    return redirect(url_for("chat"))


# ==================== Popup Q&A + Background Generation Routes ====================


@app.route("/popup_start", methods=["POST"])
@login_required
@limiter.limit(_popup_start_rate_limit, key_func=get_remote_address)
def popup_start():
    """Fetch clarifying questions for ticker + trade_type and initialize agent session."""
    ticker = (request.form.get("ticker") or "").strip().upper()
    trade_type = (request.form.get("trade_type") or "").strip()

    if not ticker or not trade_type:
        return jsonify({"error": "ticker and trade_type are required"}), 400

    session_id = get_or_create_session_id()
    agent = initialize_session(session_id)
    agent.reset_conversation()

    session["current_ticker"] = ticker
    session["current_trade_type"] = trade_type

    # Let the orchestrator agent run one turn; it will call ask_user_questions tool
    try:
        agent.start_research(ticker, trade_type)
    except Exception:
        pass
    questions = agent.pending_questions

    # Fallback if agent did not call the tool or returned malformed data
    if not isinstance(questions, list) or not questions:
        questions = [
            {
                "question": f"What is your primary goal for researching {ticker}?",
                "options": [
                    "Long-term investment",
                    "Swing trade",
                    "Day trade",
                    "General analysis",
                ],
            }
        ]

    from research_subjects import get_research_subjects_for_trade_type

    subjects = [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "priority": s.priority.get(trade_type, 99),
        }
        for s in get_research_subjects_for_trade_type(trade_type)
    ]
    return jsonify(
        {"questions": questions, "session_id": session_id, "subjects": subjects}
    )


@app.route("/start_generation", methods=["POST"])
@login_required
@limiter.limit(_report_gen_rate_limit, key_func=get_remote_address)
def start_generation():
    """Kick off background report generation with collected Q&A context."""
    data = request.get_json(force=True) or {}
    questions = data.get("questions", [])
    answers = data.get("answers", [])
    selected_subject_ids = (
        data.get("selected_subject_ids") or None
    )  # None = no user selection

    if _session_hits_report_quota():
        return _report_quota_json_error()

    session_id = get_or_create_session_id()
    agent = initialize_session(session_id)
    agent.user_id = session.get("user_id")
    agent.username = session.get("username")

    # Snapshot budget input for the background thread.
    from spend_budget import get_spend_budget_usd

    spend_budget_usd = get_spend_budget_usd(agent.user_id)

    # Build context string from Q&A pairs
    lines = []
    for i, q in enumerate(questions):
        a = answers[i] if i < len(answers) else ""
        if q:
            lines.append(f"Q: {q}")
            lines.append(f"A: {a}")
    context_str = "User context:\n" + "\n".join(lines) if lines else ""

    _generation_status[session_id] = {"status": "in_progress", "report_id": None}

    def run_generation():
        emitter = create_emitter()
        agent.set_emitter(emitter)
        try:
            agent.generate_report(
                context=context_str,
                selected_subjects=selected_subject_ids,
                spend_budget_usd=spend_budget_usd,
            )
            _generation_status[session_id] = {
                "status": "ready",
                "report_id": agent.current_report_id,
            }
        except Exception as e:
            _generation_status[session_id] = {"status": "error", "message": str(e)}
        finally:
            agent.set_emitter(None)

    threading.Thread(target=run_generation, daemon=True).start()
    return jsonify({"success": True})


@app.route("/api/report_status/<session_id>")
@login_required
def report_status(session_id: str):
    """Poll endpoint for background generation status."""
    if session.get("session_id") != session_id:
        return jsonify({"error": "forbidden"}), 403
    return jsonify(_generation_status.get(session_id, {"status": "unknown"}))


@app.route("/api/usage", methods=["GET"])
@login_required
def api_usage():
    """Monthly free-tier research report usage for the signed-in user."""
    from database import get_database_manager
    from report_usage import current_period_month, get_free_tier_report_limit

    uid = session["user_id"]
    db = get_database_manager()
    period = current_period_month()
    limit = get_free_tier_report_limit()
    if db.user_is_pro(uid):
        return jsonify(
            {
                "reports_used": 0,
                "reports_limit": None,
                "period": period,
                "is_pro": True,
            }
        )
    used = db.get_report_usage_count(uid, period)
    return jsonify(
        {
            "reports_used": used,
            "reports_limit": limit if limit > 0 else None,
            "period": period,
            "is_pro": False,
        }
    )


# ==================== Portfolio Routes ====================


@app.route("/portfolio")
@login_required
def portfolio():
    """Portfolio list page."""
    portfolio_service = get_portfolio_service()
    data = portfolio_service.get_portfolios_with_summaries(user_id=session["user_id"])
    status = pop_status()
    return render_template(
        "portfolio_list.html",
        portfolios=data["portfolios"],
        overall=data["overall"],
        **status,
        user_id=session.get("user_id", ""),
    )


@app.route("/portfolio/create", methods=["POST"])
@login_required
def create_portfolio_route():
    """Create a new portfolio."""
    name = request.form.get("name", "").strip()
    if not name:
        flash_status("Portfolio name is required", "error")
        return redirect(url_for("portfolio"))
    track_cash = request.form.get("track_cash") == "on"
    cash_balance = 0.0
    if track_cash:
        try:
            raw = request.form.get("cash_balance", "").strip().replace(",", "")
            cash_balance = float(raw) if raw else 0.0
            cash_balance = max(0.0, cash_balance)
        except (ValueError, TypeError):
            cash_balance = 0.0
    portfolio_service = get_portfolio_service()
    portfolio_id = portfolio_service.create_portfolio(
        name=name,
        user_id=session["user_id"],
        track_cash=track_cash,
        cash_balance=cash_balance,
    )
    return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))


@app.route("/portfolio/<portfolio_id>/cash", methods=["POST"])
@login_required
def update_portfolio_cash(portfolio_id: str):
    """Update cash balance for a portfolio (JSON body: { \"cash_balance\": number })."""
    portfolio_service = get_portfolio_service()
    portfolio_data = portfolio_service.get_portfolio(portfolio_id)
    if not portfolio_data or portfolio_data.get("user_id") != session["user_id"]:
        return {"ok": False, "error": "Not found"}, 404
    if not portfolio_data.get("track_cash"):
        return {"ok": False, "error": "Portfolio does not track cash"}, 400
    data = request.get_json(silent=True) or {}
    try:
        cash_balance = float(data.get("cash_balance", 0))
        if cash_balance < 0:
            return {"ok": False, "error": "Cash balance cannot be negative"}, 400
    except (TypeError, ValueError):
        return {"ok": False, "error": "Invalid cash_balance"}, 400
    try:
        portfolio_service.update_cash_balance(portfolio_id, cash_balance)
        return {"ok": True, "cash_balance": cash_balance}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


@app.route("/portfolio/<portfolio_id>")
@login_required
def portfolio_detail(portfolio_id: str):
    """Portfolio dashboard for a specific portfolio."""
    portfolio_service = get_portfolio_service()
    portfolio_data = portfolio_service.get_portfolio(portfolio_id)
    if not portfolio_data or portfolio_data.get("user_id") != session["user_id"]:
        abort(404)
    try:
        summary = portfolio_service.get_portfolio_summary(
            portfolio_id, with_prices=False
        )
        status = pop_status()
        return render_template(
            "portfolio.html",
            portfolio=portfolio_data,
            summary=summary,
            holdings=summary["holdings"],
            **status,
        )
    except Exception as e:
        flash_status(f"Error loading portfolio: {str(e)}", "error")
        return render_template(
            "portfolio.html",
            portfolio=portfolio_data,
            summary=None,
            holdings=[],
            **pop_status(),
        )


@app.route("/portfolio/<portfolio_id>/add", methods=["GET", "POST"])
@login_required
def add_transaction(portfolio_id: str):
    """Add transaction form."""
    portfolio_service = get_portfolio_service()
    portfolio_data = portfolio_service.get_portfolio(portfolio_id)
    if not portfolio_data or portfolio_data.get("user_id") != session["user_id"]:
        abort(404)

    if request.method == "POST":
        try:
            # Parse form data
            symbol = request.form.get("symbol", "").strip().upper()
            transaction_type = request.form.get("transaction_type", "")
            quantity = Decimal(request.form.get("quantity", "0"))
            price = Decimal(request.form.get("price", "0"))
            date_str = request.form.get("date", "")
            fees = Decimal(request.form.get("fees", "0") or "0")
            notes = request.form.get("notes", "")
            asset_type = request.form.get("asset_type", None)

            # Validate
            if not symbol:
                raise ValueError("Symbol is required")
            if transaction_type not in ("buy", "sell"):
                raise ValueError("Invalid transaction type")
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            if price <= 0:
                raise ValueError("Price must be positive")
            if not date_str:
                raise ValueError("Date is required")

            transaction_date = datetime.strptime(date_str, "%Y-%m-%d")

            portfolio_service.add_transaction(
                portfolio_id=portfolio_id,
                symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                price_per_unit=price,
                transaction_date=transaction_date,
                fees=fees,
                notes=notes,
                asset_type=asset_type if asset_type else None,
            )

            flash_status(
                f"Transaction added: {transaction_type.upper()} {quantity} {symbol}",
                "success",
            )

        except Exception as e:
            flash_status(f"Error: {str(e)}", "error")

        return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))

    # GET request - show form
    status = pop_status()
    return render_template("add_transaction.html", portfolio=portfolio_data, **status)


@app.route("/portfolio/<portfolio_id>/import", methods=["GET", "POST"])
@login_required
def import_csv(portfolio_id: str):
    """CSV import page."""
    portfolio_service = get_portfolio_service()
    portfolio_data = portfolio_service.get_portfolio(portfolio_id)
    if not portfolio_data or portfolio_data.get("user_id") != session["user_id"]:
        abort(404)

    if request.method == "POST":
        try:
            if "csv_file" not in request.files:
                raise ValueError("No file uploaded")

            file = request.files["csv_file"]
            if file.filename == "":
                raise ValueError("No file selected")

            file.seek(0, 2)
            if file.tell() > 10 * 1024 * 1024:
                raise ValueError("File exceeds 10MB limit")
            file.seek(0)
            csv_content = file.read().decode("utf-8")
            result = portfolio_service.import_csv(
                portfolio_id=portfolio_id,
                csv_content=csv_content,
                filename=file.filename,
            )

            session["import_summary"] = {
                "success_count": result.success_count,
                "error_count": result.error_count,
            }
            if result.error_count > 0:
                flash_status(
                    f"{result.success_count} rows imported successfully, {result.error_count} rows failed",
                    "info",
                )
                session["import_errors"] = result.errors
            else:
                flash_status(
                    f"{result.success_count} rows imported successfully, 0 rows failed",
                    "success",
                )
                session["import_errors"] = []

        except Exception as e:
            flash_status(f"Import failed: {str(e)}", "error")
            session["import_summary"] = None
            session["import_errors"] = []

        return redirect(url_for("import_csv", portfolio_id=portfolio_id))

    # GET request - show import form
    status = pop_status()
    import_summary = session.pop("import_summary", None)
    import_errors = session.pop("import_errors", None)
    return render_template(
        "import_csv.html",
        portfolio=portfolio_data,
        **status,
        import_summary=import_summary,
        import_errors=import_errors,
    )


@app.route("/portfolio/<portfolio_id>/holding/<symbol>")
@login_required
def holding_detail(portfolio_id: str, symbol: str):
    """View holding details and transactions."""
    portfolio_service = get_portfolio_service()
    portfolio_data = portfolio_service.get_portfolio(portfolio_id)
    if not portfolio_data or portfolio_data.get("user_id") != session["user_id"]:
        abort(404)

    try:
        holding = portfolio_service.get_holding(portfolio_id, symbol)

        if not holding:
            flash_status(f"Holding not found: {symbol}", "info")
            return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))

        if holding.get("total_quantity", Decimal("0")) <= Decimal("0"):
            flash_status(
                f"{symbol} is a closed position with no remaining quantity.", "info"
            )
            return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))

        transactions = portfolio_service.get_transactions(holding["holding_id"])

        # Get current price
        provider, _ = DataProviderFactory.get_provider_for_symbol(symbol)
        current_price = provider.get_current_price(symbol) or Decimal("0")

        holding["current_price"] = current_price
        holding["market_value"] = holding["total_quantity"] * current_price
        holding["unrealized_gain"] = (
            holding["market_value"] - holding["total_cost_basis"]
        )

        if holding["total_cost_basis"] > 0:
            holding["unrealized_gain_pct"] = (
                holding["unrealized_gain"] / holding["total_cost_basis"]
            ) * 100
        else:
            holding["unrealized_gain_pct"] = Decimal("0")

        status = pop_status()

        return render_template(
            "holding_detail.html",
            portfolio=portfolio_data,
            holding=holding,
            transactions=transactions,
            **status,
        )

    except Exception as e:
        flash_status(f"Error: {str(e)}", "error")
        return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))


@app.route(
    "/portfolio/<portfolio_id>/transaction/<transaction_id>/delete", methods=["POST"]
)
@login_required
def delete_transaction(portfolio_id: str, transaction_id: str):
    """Delete a transaction."""
    try:
        portfolio_service = get_portfolio_service()

        txn = portfolio_service.get_transaction(transaction_id)
        if not txn:
            flash_status("Transaction not found", "error")
            return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))

        holding = portfolio_service.get_holding_by_id(txn["holding_id"])
        if not holding or holding.get("portfolio_id") != portfolio_id:
            flash_status("Transaction not found", "error")
            return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))

        portfolio = portfolio_service.get_portfolio(holding["portfolio_id"])
        if not portfolio or portfolio.get("user_id") != session["user_id"]:
            flash_status("Not authorized", "error")
            return redirect(url_for("portfolio"))

        symbol = holding["symbol"]
        if portfolio_service.delete_transaction(transaction_id):
            flash_status("Transaction deleted", "success")
        else:
            flash_status("Failed to delete transaction", "error")

        if symbol:
            return redirect(
                url_for("holding_detail", portfolio_id=portfolio_id, symbol=symbol)
            )

    except Exception as e:
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            raise
        flash_status(f"Error: {str(e)}", "error")

    return redirect(url_for("portfolio_detail", portfolio_id=portfolio_id))


@app.route("/api/portfolios/prices")
@login_required
def portfolios_prices():
    """Return live price summaries for all user portfolios (for async list page)."""
    portfolio_service = get_portfolio_service()
    portfolios = portfolio_service.list_portfolios(user_id=session["user_id"])

    def to_float(v):
        return float(v) if v is not None else None

    result = []
    for p in portfolios:
        pid = p["portfolio_id"]
        try:
            summary = portfolio_service.get_portfolio_summary(pid, with_prices=True)
            result.append(
                {
                    "portfolio_id": pid,
                    "total_market_value": to_float(summary.get("total_market_value")),
                    "total_unrealized_gain": to_float(
                        summary.get("total_unrealized_gain")
                    ),
                    "total_unrealized_gain_pct": to_float(
                        summary.get("total_unrealized_gain_pct")
                    ),
                }
            )
        except Exception:
            result.append(
                {
                    "portfolio_id": pid,
                    "total_market_value": None,
                    "total_unrealized_gain": None,
                    "total_unrealized_gain_pct": None,
                }
            )

    return jsonify(result)


@app.route("/api/portfolio/<portfolio_id>/prices")
@login_required
def portfolio_prices(portfolio_id):
    """Return live prices and computed P&L for all holdings as JSON."""
    portfolio_service = get_portfolio_service()
    portfolio_data = portfolio_service.get_portfolio(portfolio_id)
    if not portfolio_data or portfolio_data.get("user_id") != session["user_id"]:
        return jsonify({"error": "Not found"}), 404

    summary = portfolio_service.get_portfolio_summary(portfolio_id, with_prices=True)
    breakdowns = {}
    try:
        breakdowns = portfolio_service.get_allocation_breakdowns_from_summary(summary)
        if not isinstance(breakdowns, dict):
            breakdowns = {}
    except Exception:
        breakdowns = {
            "prices_loaded": bool(summary.get("prices_loaded")),
            "sector": [],
            "market": [],
        }

    def to_float(v):
        return float(v) if v is not None else None

    holdings_out = []
    for h in summary["holdings"]:
        holdings_out.append(
            {
                "symbol": h["symbol"],
                "price_available": h.get("price_available", False),
                "current_price": to_float(h.get("current_price")),
                "market_value": to_float(h.get("market_value")),
                "unrealized_gain": to_float(h.get("unrealized_gain")),
                "unrealized_gain_pct": to_float(h.get("unrealized_gain_pct")),
            }
        )

    return jsonify(
        {
            "holdings": holdings_out,
            "total_market_value": to_float(summary.get("total_market_value")),
            "total_unrealized_gain": to_float(summary.get("total_unrealized_gain")),
            "total_unrealized_gain_pct": to_float(
                summary.get("total_unrealized_gain_pct")
            ),
            "stock_allocation_pct": to_float(summary.get("stock_allocation_pct")),
            "crypto_allocation_pct": to_float(summary.get("crypto_allocation_pct")),
            "cash_allocation_pct": to_float(summary.get("cash_allocation_pct")),
            "breakdowns": {
                "sector": breakdowns.get("sector", []),
                "market": breakdowns.get("market", []),
                "prices_loaded": bool(breakdowns.get("prices_loaded")),
            },
        }
    )


@app.route("/api/portfolio/<portfolio_id>/history")
@login_required
def portfolio_history(portfolio_id):
    """Return monthly portfolio value history as JSON."""
    portfolio = get_portfolio_service().get_portfolio(portfolio_id)
    if not portfolio or portfolio.get("user_id") != session["user_id"]:
        return jsonify({"error": "Not found"}), 404
    history_service = get_history_service()
    data = history_service.get_monthly_values(portfolio_id)
    return jsonify(data)


# ============================================================================
# Price alerts (Phase 2 — STOA-16; persistence + evaluation + in-app notifications)
# ============================================================================


def _alert_row_to_json(row):
    if not row:
        return None
    return {
        "alert_id": row["alert_id"],
        "symbol": row["symbol"],
        "asset_type": row["asset_type"],
        "direction": row["direction"],
        "target_price": (
            float(row["target_price"]) if row.get("target_price") is not None else None
        ),
        "active": bool(row["active"]),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "last_triggered_at": (
            row["last_triggered_at"].isoformat()
            if row.get("last_triggered_at")
            else None
        ),
    }


@app.route("/api/alerts", methods=["GET"])
@login_required
def api_list_alerts():
    from database import get_database_manager

    db = get_database_manager()
    rows = db.list_price_alerts_for_user(session["user_id"])
    return jsonify({"success": True, "alerts": [_alert_row_to_json(r) for r in rows]})


@app.route("/api/alerts", methods=["POST"])
@login_required
def api_create_alert():
    from database import get_database_manager

    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").strip().upper()
    direction = (data.get("direction") or "").strip().lower()
    if not symbol:
        return jsonify({"success": False, "error": "symbol is required"}), 400
    if direction not in ("above", "below"):
        return (
            jsonify({"success": False, "error": "direction must be above or below"}),
            400,
        )
    try:
        target_price = float(data.get("target_price"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "invalid target_price"}), 400
    if target_price <= 0:
        return (
            jsonify({"success": False, "error": "target_price must be positive"}),
            400,
        )
    asset_type = (data.get("asset_type") or "stock").strip().lower()
    if asset_type not in ("stock", "crypto"):
        return jsonify({"success": False, "error": "invalid asset_type"}), 400

    alert_id = str(uuid.uuid4())
    db = get_database_manager()
    db.create_price_alert(
        alert_id=alert_id,
        user_id=session["user_id"],
        symbol=symbol,
        direction=direction,
        target_price=target_price,
        asset_type=asset_type,
    )
    return jsonify({"success": True, "alert_id": alert_id})


@app.route("/api/alerts/<alert_id>", methods=["DELETE"])
@login_required
def api_delete_alert(alert_id):
    from database import get_database_manager

    db = get_database_manager()
    if not db.delete_price_alert(alert_id, session["user_id"]):
        return jsonify({"success": False, "error": "Not found"}), 404
    return jsonify({"success": True})


@app.route("/api/alerts/<alert_id>", methods=["PATCH"])
@login_required
def api_patch_alert(alert_id):
    from database import get_database_manager

    data = request.get_json(silent=True) or {}
    if "active" not in data:
        return jsonify({"success": False, "error": "active field required"}), 400
    active = bool(data.get("active"))
    db = get_database_manager()
    if not db.set_price_alert_active(alert_id, session["user_id"], active):
        return jsonify({"success": False, "error": "Not found"}), 404
    return jsonify({"success": True})


def _alert_notification_row_to_json(row):
    if not row:
        return None
    return {
        "notification_id": row["notification_id"],
        "alert_id": row["alert_id"],
        "symbol": row["symbol"],
        "body": row["body"],
        "read_at": row["read_at"].isoformat() if row.get("read_at") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


@app.route("/api/alerts/notifications", methods=["GET"])
@login_required
def api_list_alert_notifications():
    from database import get_database_manager

    db = get_database_manager()
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    uid = session["user_id"]
    rows = db.list_price_alert_notifications_for_user(uid, limit=limit)
    unread = db.count_unread_price_alert_notifications(uid)
    return jsonify(
        {
            "success": True,
            "notifications": [_alert_notification_row_to_json(r) for r in rows],
            "unread_count": unread,
        }
    )


@app.route("/api/alerts/notifications/<notification_id>", methods=["PATCH"])
@login_required
def api_patch_alert_notification(notification_id):
    from database import get_database_manager

    data = request.get_json(silent=True) or {}
    if not data.get("read"):
        return jsonify({"success": False, "error": "read: true required"}), 400
    db = get_database_manager()
    if not db.mark_price_alert_notification_read(notification_id, session["user_id"]):
        return jsonify({"success": False, "error": "Not found"}), 404
    return jsonify({"success": True})


# ============================================================================
# Telegram linking (STOA-35)
# ============================================================================


@app.route("/api/telegram/connect-token", methods=["GET"])
@login_required
def api_telegram_connect_token():
    """Generate a short-lived token a user can paste into Telegram `/connect <token>`."""
    from database import get_database_manager

    db = get_database_manager()
    token = db.create_telegram_connect_token(session["user_id"], ttl_minutes=10)
    return jsonify({"success": True, "token": token, "ttl_minutes": 10})


# ============================================================================
# Report History & Export Routes
# ============================================================================
@app.route("/reports")
@login_required
def report_history():
    """Render the report history page with filters."""
    get_or_create_session_id()

    # Get filter parameters from query string
    ticker = request.args.get("ticker", "").strip().upper() or None
    trade_type = request.args.get("trade_type", "").strip() or None
    sort_order = request.args.get("sort", "DESC").upper()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 12

    # Calculate offset
    offset = (page - 1) * per_page

    try:
        storage = ReportStorage()
        user_id = session.get("user_id")
        reports, total_count = storage.get_all_reports(
            ticker=ticker,
            trade_type=trade_type,
            sort_order=sort_order,
            limit=per_page,
            offset=offset,
            user_id=user_id,
        )

        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        return render_template(
            "reports.html",
            reports=reports,
            total_count=total_count,
            current_page=page,
            total_pages=total_pages,
            per_page=per_page,
            filter_ticker=ticker or "",
            filter_trade_type=trade_type or "",
            sort_order=sort_order,
            page_range=_page_range(page, total_pages),
        )
    except Exception as e:
        return render_template(
            "reports.html",
            reports=[],
            total_count=0,
            current_page=1,
            total_pages=1,
            per_page=per_page,
            filter_ticker="",
            filter_trade_type="",
            sort_order="DESC",
            page_range=[1],
            error=str(e),
        )


@app.route("/api/news")
def api_news():
    from news_service import get_briefing

    return jsonify(get_briefing())


@app.route("/api/news/more")
def api_news_more():
    from news_service import get_more

    return jsonify(get_more())


@app.route("/api/reports")
@login_required
def api_reports():
    """AJAX endpoint for filtered reports (returns JSON)."""
    ticker = request.args.get("ticker", "").strip().upper() or None
    trade_type = request.args.get("trade_type", "").strip() or None
    sort_order = request.args.get("sort", "DESC").upper()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 12

    offset = (page - 1) * per_page

    try:
        storage = ReportStorage()
        user_id = session.get("user_id")
        reports, total_count = storage.get_all_reports(
            ticker=ticker,
            trade_type=trade_type,
            sort_order=sort_order,
            limit=per_page,
            offset=offset,
            user_id=user_id,
        )

        # Convert datetime objects to ISO strings for JSON
        for report in reports:
            if report.get("created_at"):
                report["created_at"] = report["created_at"].isoformat()

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        return jsonify(
            {
                "success": True,
                "reports": reports,
                "total_count": total_count,
                "current_page": page,
                "total_pages": total_pages,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/report/<report_id>")
@login_required
def view_report(report_id):
    """View a single report."""
    try:
        storage = ReportStorage()
        report = storage.get_report(report_id, user_id=session.get("user_id"))

        if not report:
            abort(404)

        return render_template("report_view.html", report=report)
    except Exception as e:
        app.logger.error(f"Error loading report {report_id}: {e}")
        abort(500)


@app.route("/report/<report_id>/pdf")
@login_required
def download_report_pdf(report_id):
    """Download report as PDF."""
    try:
        storage = ReportStorage()
        report = storage.get_report(report_id, user_id=session.get("user_id"))

        if not report:
            abort(404)

        # Generate PDF
        pdf_generator = get_pdf_generator()
        pdf_bytes = pdf_generator.generate_pdf(
            ticker=report["ticker"],
            trade_type=report["trade_type"],
            report_text=report["report_text"],
            created_at=report.get("created_at"),
        )

        # Create filename
        filename = f"{report['ticker']}_report_{report_id[:8]}.pdf"

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": len(pdf_bytes),
            },
        )
    except Exception as e:
        app.logger.error(f"Error generating PDF for report {report_id}: {e}")
        abort(500)


@app.route("/report/<report_id>/chat")
@login_required
def chat_with_report(report_id):
    """Open chat interface with report context pre-loaded."""
    try:
        storage = ReportStorage()
        report = storage.get_report(report_id, user_id=session.get("user_id"))

        if not report:
            abort(404)

        # Store report context in session for chat
        session["current_report_id"] = report_id
        session["current_ticker"] = report["ticker"]
        session["current_trade_type"] = report["trade_type"]

        # Initialize conversation with report context
        session["conversation_history"] = [
            {
                "role": "assistant",
                "content": f"I've loaded the research report for **{report['ticker']}** ({report['trade_type']}). "
                f"Feel free to ask me any questions about this analysis!",
            }
        ]
        flash_status(f'Report loaded: {report["ticker"]}', "success")

        return redirect(url_for("chat"))
    except Exception as e:
        flash_status(f"Error loading report: {str(e)}", "error")
        return redirect(url_for("report_history"))


# ==================== Ticker-Centric Report View & Notes ====================


@app.route("/ticker/<symbol>")
@login_required
def ticker_detail(symbol: str):
    """Ticker-centric page showing all reports + per-user notes."""
    from database import get_database_manager

    symbol = (symbol or "").strip().upper()
    if not symbol:
        abort(404)

    get_or_create_session_id()

    storage = ReportStorage()
    user_id = session.get("user_id")

    reports, _ = storage.get_all_reports(
        ticker=symbol,
        trade_type=None,
        sort_order="DESC",
        limit=50,
        offset=0,
        user_id=user_id,
    )

    db = get_database_manager()
    raw_notes = db.get_ticker_note(user_id, symbol) if user_id else None

    return render_template(
        "ticker.html",
        symbol=symbol,
        reports=reports,
        notes_content=raw_notes or "",
    )


@app.route("/ticker/<symbol>/notes", methods=["POST"])
@login_required
def save_ticker_notes(symbol: str):
    """Persist rich-text ticker notes for the current user."""
    from database import get_database_manager

    symbol = (symbol or "").strip().upper()
    if not symbol:
        abort(404)

    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("sign_in"))

    raw_content = request.form.get("content", "") or ""
    cleaned = bleach.clean(
        raw_content,
        tags=_MD_ALLOWED_TAGS,
        attributes=_MD_ALLOWED_ATTRS,
        strip=True,
    )

    db = get_database_manager()
    db.upsert_ticker_note(user_id, symbol, cleaned)
    flash_status(f"Notes updated for {symbol}.", "success")
    return redirect(url_for("ticker_detail", symbol=symbol))


# ==================== Watchlist Routes ====================


@app.route("/watchlist")
@login_required
def watchlist():
    """Main watchlist page — auto-creates default watchlist if none exist."""
    try:
        watchlist_svc = get_watchlist_service()
        user_id = session["user_id"]
        watchlists = watchlist_svc.list_watchlists(user_id)

        # Auto-create default
        if not watchlists:
            watchlist_svc.get_or_create_default_watchlist(user_id)
            watchlists = watchlist_svc.list_watchlists(user_id)

        active_watchlist_id = request.args.get(
            "wl", watchlists[0]["watchlist_id"] if watchlists else None
        )
        active_watchlist = None
        if active_watchlist_id:
            # Ownership check
            wl = watchlist_svc.db.get_watchlist(active_watchlist_id)
            if wl and wl["user_id"] == user_id:
                active_watchlist = watchlist_svc.get_watchlist_with_items(
                    active_watchlist_id
                )

        status = pop_status()
        return render_template(
            "watchlist.html",
            watchlists=watchlists,
            active_watchlist=active_watchlist,
            **status,
        )
    except Exception as e:
        return render_template(
            "watchlist.html",
            watchlists=[],
            active_watchlist=None,
            status_message=f"Error loading watchlist: {str(e)}",
            status_type="error",
        )


@app.route("/watchlist/create", methods=["POST"])
@login_required
def watchlist_create():
    name = request.form.get("name", "").strip() or "My Watchlist"
    try:
        watchlist_svc = get_watchlist_service()
        wl_id = watchlist_svc.create_watchlist(session["user_id"], name)
        flash_status(f'Watchlist "{name}" created', "success")
        return redirect(url_for("watchlist", wl=wl_id))
    except Exception as e:
        flash_status(f"Error: {str(e)}", "error")
        return redirect(url_for("watchlist"))


@app.route("/watchlist/<watchlist_id>/rename", methods=["POST"])
@login_required
def watchlist_rename(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl["user_id"] != session["user_id"]:
        abort(403)
    name = request.form.get("name", "").strip()
    if name:
        watchlist_svc.rename_watchlist(watchlist_id, name)
        flash_status(f'Renamed to "{name}"', "success")
    return redirect(url_for("watchlist", wl=watchlist_id))


@app.route("/watchlist/<watchlist_id>/delete", methods=["POST"])
@login_required
def watchlist_delete(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl["user_id"] != session["user_id"]:
        abort(403)
    watchlist_svc.delete_watchlist(watchlist_id)
    flash_status("Watchlist deleted", "success")
    return redirect(url_for("watchlist"))


@app.route("/watchlist/<watchlist_id>/add-symbol", methods=["POST"])
@login_required
def watchlist_add_symbol(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl["user_id"] != session["user_id"]:
        abort(403)
    symbol = request.form.get("symbol", "").strip().upper()
    section_id = request.form.get("section_id") or None
    if not symbol:
        flash_status("Symbol is required", "error")
        return redirect(url_for("watchlist", wl=watchlist_id))
    try:
        watchlist_svc.add_symbol(watchlist_id, symbol, section_id)
        flash_status(f"{symbol} added to watchlist", "success")
    except ValueError as e:
        flash_status(str(e), "error")
    except Exception as e:
        flash_status(f"Error adding {symbol}: {str(e)}", "error")
    return redirect(url_for("watchlist", wl=watchlist_id))


@app.route("/watchlist/item/<item_id>/remove", methods=["POST"])
@login_required
def watchlist_remove_item(item_id):
    watchlist_svc = get_watchlist_service()
    # Find which watchlist this item belongs to for ownership check + redirect
    from database import get_database_manager

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT wi.watchlist_id, wl.user_id
                FROM watchlist_items wi
                JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                WHERE wi.item_id = %s
            """,
                (item_id,),
            )
            row = cur.fetchone()
    finally:
        db._release(conn)

    if not row or row["user_id"] != session["user_id"]:
        abort(403)

    watchlist_id = row["watchlist_id"]
    watchlist_svc.remove_symbol(item_id)
    flash_status("Symbol removed", "success")
    return redirect(url_for("watchlist", wl=watchlist_id))


@app.route("/watchlist/item/<item_id>/pin", methods=["POST"])
@login_required
def watchlist_toggle_pin(item_id):
    watchlist_svc = get_watchlist_service()
    from database import get_database_manager

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT wi.watchlist_id, wi.is_pinned, wl.user_id
                FROM watchlist_items wi
                JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                WHERE wi.item_id = %s
            """,
                (item_id,),
            )
            row = cur.fetchone()
    finally:
        db._release(conn)

    if not row or row["user_id"] != session["user_id"]:
        abort(403)

    watchlist_id = row["watchlist_id"]
    user_id = session["user_id"]

    try:
        if row["is_pinned"]:
            watchlist_svc.unpin_item(item_id)
            flash_status("Unpinned from homepage", "success")
        else:
            watchlist_svc.pin_item(user_id, item_id)
            flash_status("Pinned to homepage", "success")
    except ValueError as e:
        flash_status(str(e), "error")

    return redirect(url_for("watchlist", wl=watchlist_id))


@app.route("/watchlist/<watchlist_id>/section/create", methods=["POST"])
@login_required
def watchlist_create_section(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl["user_id"] != session["user_id"]:
        abort(403)
    name = request.form.get("name", "").strip()
    if name:
        try:
            watchlist_svc.create_section(watchlist_id, name)
            flash_status(f'Section "{name}" created', "success")
        except Exception as e:
            flash_status(f"Error creating section: {str(e)}", "error")
    return redirect(url_for("watchlist", wl=watchlist_id))


@app.route("/watchlist/section/<section_id>/rename", methods=["POST"])
@login_required
def watchlist_rename_section(section_id):
    watchlist_svc = get_watchlist_service()
    from database import get_database_manager

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT ws.watchlist_id, wl.user_id
                FROM watchlist_sections ws
                JOIN watchlists wl ON ws.watchlist_id = wl.watchlist_id
                WHERE ws.section_id = %s
            """,
                (section_id,),
            )
            row = cur.fetchone()
    finally:
        db._release(conn)

    if not row or row["user_id"] != session["user_id"]:
        abort(403)

    name = request.form.get("name", "").strip()
    if name:
        watchlist_svc.rename_section(section_id, name)
        flash_status(f'Section renamed to "{name}"', "success")
    return redirect(url_for("watchlist", wl=row["watchlist_id"]))


@app.route("/watchlist/section/<section_id>/delete", methods=["POST"])
@login_required
def watchlist_delete_section(section_id):
    watchlist_svc = get_watchlist_service()
    from database import get_database_manager

    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT ws.watchlist_id, wl.user_id
                FROM watchlist_sections ws
                JOIN watchlists wl ON ws.watchlist_id = wl.watchlist_id
                WHERE ws.section_id = %s
            """,
                (section_id,),
            )
            row = cur.fetchone()
    finally:
        db._release(conn)

    if not row or row["user_id"] != session["user_id"]:
        abort(403)

    watchlist_svc.delete_section(section_id)
    flash_status("Section deleted", "success")
    return redirect(url_for("watchlist", wl=row["watchlist_id"]))


@app.route("/api/watchlist/<watchlist_id>/news-recap", methods=["GET"])
@login_required
@limiter.limit(lambda: os.getenv("STOCKPRO_RATE_LIMIT_WATCHLIST_NEWS_RECAP", "30 per hour"), key_func=get_remote_address)
def api_watchlist_news_recap(watchlist_id: str):
    """Return a compact digest of recent news for all symbols in a watchlist."""
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl["user_id"] != session["user_id"]:
        abort(403)

    items = watchlist_svc.db.get_watchlist_items(watchlist_id) or []
    symbols = [row.get("symbol") for row in items if isinstance(row, dict)]

    from watchlist.news_recap_service import get_watchlist_news_recap

    try:
        digest = get_watchlist_news_recap(
            user_id=session["user_id"], watchlist_id=watchlist_id, symbols=symbols
        )
        return jsonify({"success": True, "items": digest})
    except Exception as e:
        app.logger.warning("watchlist news recap failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": "Failed to fetch news recap"}), 500


@app.route("/api/watchlist/<watchlist_id>/earnings", methods=["GET"])
@login_required
@limiter.limit(
    lambda: os.getenv("STOCKPRO_RATE_LIMIT_WATCHLIST_EARNINGS", "30 per hour"),
    key_func=get_remote_address,
)
def api_watchlist_earnings_calendar(watchlist_id: str):
    """Return upcoming earnings calendar for all symbols in a watchlist."""
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl["user_id"] != session["user_id"]:
        abort(403)

    items = watchlist_svc.db.get_watchlist_items(watchlist_id) or []
    symbols = [row.get("symbol") for row in items if isinstance(row, dict)]

    from watchlist.earnings_calendar_service import get_watchlist_earnings_calendar

    try:
        calendar = get_watchlist_earnings_calendar(
            user_id=session["user_id"],
            watchlist_id=watchlist_id,
            symbols=symbols,
        )
        return jsonify({"success": True, "items": calendar})
    except Exception as e:
        app.logger.warning("watchlist earnings calendar failed: %s", e, exc_info=True)
        return (
            jsonify({"success": False, "error": "Failed to fetch earnings calendar"}),
            500,
        )


try:
    from realtime.ws_prices import register_ws_routes

    register_ws_routes(app)
except ImportError as e:
    app.logger.warning("WebSocket /ws/prices not registered: %s", e)


def main():
    """Main entry point for the Flask app."""
    # Check for required environment variables
    if not os.getenv("GEMINI_API_KEY"):
        app.logger.warning(
            "GEMINI_API_KEY not set — research and embeddings will fail until it is configured."
        )

    from watchlist.price_refresh import start_price_refresh

    start_price_refresh()

    app.run(host="127.0.0.1", port=int(os.getenv("PORT", 5000)), debug=True)


if __name__ == "__main__":
    main()
