"""
Flask web interface for the Stock Research AI Agent.
"""

import sys
from pathlib import Path

# Add project root to Python path to allow imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, abort
from flask_wtf.csrf import CSRFProtect
from clerk_backend_api import Clerk as ClerkClient, AuthenticateRequestOptions
import os
import re
import threading
import queue
import json
import time
from functools import wraps
from dotenv import load_dotenv
import uuid
import bleach
import markdown as md_lib
from markupsafe import Markup
from decimal import Decimal
from datetime import datetime

from orchestrator_graph import create_session, OrchestratorSession
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
_clerk_secret_key_raw = os.getenv('CLERK_SECRET_KEY')
if not _clerk_secret_key_raw:
    raise RuntimeError("CLERK_SECRET_KEY environment variable is not set")
_clerk_jwt_key_raw = os.getenv('CLERK_JWT_KEY')
if not _clerk_jwt_key_raw:
    raise RuntimeError("CLERK_JWT_KEY environment variable is not set")
clerk_client = ClerkClient(bearer_auth=_clerk_secret_key_raw)
CLERK_JWT_KEY = _clerk_jwt_key_raw.replace('\\n', '\n')

# Create Flask app
# Set template and static folders explicitly to point to project root
app = Flask(__name__, 
            template_folder=str(project_root / 'templates'), 
            static_folder=str(project_root / 'static'))
_secret_key = os.getenv('FLASK_SECRET_KEY')
if not _secret_key:
    raise RuntimeError("FLASK_SECRET_KEY environment variable is not set")
app.secret_key = _secret_key
csrf = CSRFProtect(app)

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, app=app, default_limits=[], storage_uri="memory://")


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' in session:
            return f(*args, **kwargs)
        # Verify Clerk session token via authenticate_request
        request_state = clerk_client.authenticate_request(
            request,
            AuthenticateRequestOptions(jwt_key=CLERK_JWT_KEY)
        )
        if request_state.is_authenticated:
            clerk_user_id = request_state.payload['sub']
            if 'user_id' not in session or session['user_id'] != clerk_user_id:
                # Upsert user in MySQL
                from database import get_database_manager
                db = get_database_manager()
                user = db.get_user_by_id(clerk_user_id)
                if not user:
                    clerk_user = clerk_client.users.get(user_id=clerk_user_id)
                    email = ''
                    username = clerk_user_id
                    if clerk_user.email_addresses:
                        email = clerk_user.email_addresses[0].email_address or ''
                    if clerk_user.username:
                        username = clerk_user.username
                    elif clerk_user.first_name or clerk_user.last_name:
                        username = f"{clerk_user.first_name or ''}{clerk_user.last_name or ''}".strip() or clerk_user_id
                    db.create_user(user_id=clerk_user_id, username=username, email=email)
                else:
                    username = user.get('username', clerk_user_id)
                session['user_id'] = clerk_user_id
                session['username'] = username
                get_or_create_session_id()
            return f(*args, **kwargs)
        app.logger.warning("Clerk auth failed: %s", request_state.reason)
        return redirect(url_for('sign_in'))
    return decorated


@app.context_processor
def inject_user():
    return {
        'current_user': {
            'is_authenticated': 'user_id' in session,
            'user_id': session.get('user_id'),
            'username': session.get('username'),
        },
        'clerk_publishable_key': os.getenv('CLERK_PUBLISHABLE_KEY', ''),
    }



_MD_ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'pre', 'code', 'blockquote', 'table', 'thead',
    'tbody', 'tr', 'th', 'td', 'hr', 'br', 'ul', 'ol', 'li',
]
_MD_ALLOWED_ATTRS = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, '*': ['class']}

@app.template_filter('markdown')
def markdown_filter(text):
    raw_html = md_lib.markdown(text or '', extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists'])
    return Markup(bleach.clean(raw_html, tags=_MD_ALLOWED_TAGS, attributes=_MD_ALLOWED_ATTRS, strip=True))


@app.template_filter('markdown_preview')
def markdown_preview_filter(text, length=250):
    if not text:
        return ''
    text = re.sub(r'#{1,6}\s+', '', text)
    text = re.sub(r'\*{1,2}([^*\n]+)\*{1,2}', r'\1', text)
    text = re.sub(r'_([^_\n]+)_', r'\1', text)
    text = re.sub(r'`[^`\n]+`', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)
    text = ' '.join(text.split())
    return text[:length] + ('...' if len(text) > length else '')


def _page_range(current, total, delta=2):
    pages = sorted({1, total} | set(range(max(1, current - delta), min(total, current + delta) + 1)))
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
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


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
        llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3, max_output_tokens=400)
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
    return [{"question": f"What is your primary goal for researching {ticker}?",
             "options": ["Long-term investment", "Swing trade", "Day trade", "General analysis"]}]


# ==================== Auth Routes ====================

def _safe_redirect_url(next_url, fallback='/'):
    """Allow only relative paths to prevent open redirects."""
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return fallback


@app.route('/sign-in')
def sign_in():
    """Sign-in page (Clerk hosted component)."""
    if 'user_id' in session:
        return redirect(url_for('index'))
    next_url = request.args.get('next', '')
    return render_template('sign_in.html', next_url=_safe_redirect_url(next_url, '/'))


@app.route('/auth/sso-callback')
def auth_sso_callback():
    """OAuth/SSO callback: ClerkJS runs handleRedirectCallback here to set __session cookie, then redirects."""
    next_url = request.args.get('next', '')
    redirect_url = _safe_redirect_url(next_url, '/')
    return render_template('auth_sso_callback.html', redirect_url=redirect_url)


@app.route('/sign-up')
def sign_up():
    """Sign-up page (Clerk hosted component)."""
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('sign_up.html')


@app.route('/sign-out')
def sign_out():
    """Sign out: clear Flask session and redirect to sign-in."""
    session.clear()
    return redirect(url_for('sign_in'))


@app.route('/')
@login_required
def index():
    """Render the main landing page."""
    # Initialize session ID if needed
    get_or_create_session_id()

    # Get current values from session for form pre-filling
    current_ticker = session.get('current_ticker', '')
    current_trade_type = session.get('current_trade_type', 'Investment')

    # Pinned tickers for Market Overview (None for guests — section hidden)
    pinned_tickers = None
    user_id = session.get('user_id')
    if user_id:
        try:
            watchlist_svc = get_watchlist_service()
            pinned_tickers = watchlist_svc.get_pinned_tickers(user_id)
        except Exception:
            pinned_tickers = None

    return render_template(
        'index.html',
        current_ticker=current_ticker,
        current_trade_type=current_trade_type,
        pinned_tickers=pinned_tickers
    )


@app.route('/chat')
@login_required
def chat():
    """Render the chat interface."""
    # Initialize session ID if needed
    get_or_create_session_id()
    
    # Get conversation history from session
    conversation_history = session.get('conversation_history', [])
    current_ticker = session.get('current_ticker', '')
    current_trade_type = session.get('current_trade_type', 'Investment')
    
    return render_template(
        'chat.html',
        conversation_history=conversation_history,
        current_ticker=current_ticker,
        current_trade_type=current_trade_type
    )


@app.route('/start_research', methods=['POST'])
@login_required
def start_research():
    """Handle form submission to start research."""
    ticker = request.form.get('ticker', '').strip()
    trade_type = request.form.get('trade_type', '')
    
    # Validate input
    if not ticker:
        session['status_message'] = '❌ Please enter a stock ticker.'
        return redirect(url_for('index'))
    
    if not trade_type:
        session['status_message'] = '❌ Please select a trade type.'
        return redirect(url_for('index'))
    
    ticker = ticker.upper()
    
    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)
        agent.reset_conversation()
        
        # Start research
        response = agent.start_research(ticker, trade_type)
        
        # Store conversation in session as list of message dicts
        conversation_history = [
            {"role": "assistant", "content": response}
        ]
        
        session['conversation_history'] = conversation_history
        session['current_ticker'] = ticker
        session['current_trade_type'] = trade_type
        session['status_message'] = f'✅ Research started for {ticker} ({trade_type})'
        
    except Exception as e:
        session['status_message'] = f'❌ Error: {str(e)}'
        session['conversation_history'] = []
    
    return redirect(url_for('chat'))


@app.route('/continue', methods=['POST'])
@login_required
def continue_conversation():
    """Start a conversation turn in a background thread; return SSE session info."""
    user_input = request.form.get('user_response', '').strip()

    if not user_input:
        return jsonify({'success': False, 'error': '⚠️ Please enter a response.'}), 400

    session_id = get_or_create_session_id()
    agent = initialize_session(session_id)
    agent.user_id = session.get('user_id')

    # Snapshot mutable session state so the background thread can read it safely
    previous_report_id = session.get('current_report_id')
    conversation_history_snapshot = list(session.get('conversation_history', []))
    ticker = session.get('current_ticker', '')
    trade_type = session.get('current_trade_type', 'Investment')

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
                report_text = getattr(agent, 'last_report_text', None) or ''
                if report_text:
                    report_preview = f"# Research Report\n\n{report_text}"
                    new_history.append({"role": "assistant", "content": report_preview})
                    report_generated = True

            step_q.put({
                "type": "done",
                "user_message": user_input,
                "assistant_message": response,
                "conversation_history": new_history,
                "report_generated": report_generated,
                "report_preview": report_preview,
                "current_report_id": current_report_id,
                "report_text": getattr(agent, 'last_report_text', None) or '',
            })
        except Exception as e:
            step_q.put({"type": "error", "message": str(e)})
        finally:
            agent.set_emitter(None)

    t = threading.Thread(target=run_in_background, daemon=True)
    t.start()

    return jsonify({'success': True, 'streaming': True, 'session_id': session_id})


@app.route('/stream/<session_id>')
@login_required
def stream_steps(session_id: str):
    """SSE endpoint — streams step messages until 'done' or 'error'."""
    if session.get('session_id') != session_id:
        abort(403)

    step_q = _sse_queues.get(session_id)
    if step_q is None:
        # No active stream — send immediate done with empty payload
        def empty():
            yield "data: {\"type\": \"done\"}\n\n"
        return Response(empty(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

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
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@app.route('/commit_session', methods=['POST'])
@login_required
def commit_session():
    """Persist state from SSE 'done' payload back into the Flask session."""
    data = request.get_json(force=True) or {}
    if 'conversation_history' in data:
        session['conversation_history'] = data['conversation_history']
    if 'current_report_id' in data and data['current_report_id']:
        session['current_report_id'] = data['current_report_id']
    if 'report_text' in data and data['report_text']:
        session['report_text'] = data['report_text']
    return jsonify({'success': True})


@app.route('/generate_report', methods=['POST'])
@login_required
def generate_report():
    """Handle form submission to generate report after followup questions."""
    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)
        
        # Extract context from conversation history
        conversation_history = session.get('conversation_history', [])
        context = ""
        for msg in conversation_history:
            if msg.get('role') == 'user':
                context += f"User: {msg.get('content', '')}\n"
        
        # Generate report
        session['status_message'] = '🔄 Generating report... This may take a few minutes.'
        session['conversation_history'] = conversation_history  # Preserve history
        session.modified = True
        
        report_text = agent.generate_report(context=context)
        report_id = agent.current_report_id
        
        # Store report in session
        session['current_report_id'] = report_id
        session['report_text'] = report_text
        session['status_message'] = f'✅ Report generated successfully! Report ID: {report_id[:8]}...'
        
        # Add full report to conversation
        report_preview = f"# Research Report\n\n{report_text}"
        conversation_history.append({
            "role": "assistant",
            "content": report_preview
        })
        session['conversation_history'] = conversation_history
        
    except Exception as e:
        session['status_message'] = f'❌ Error generating report: {str(e)}'
    
    return redirect(url_for('chat'))


@app.route('/chat_report', methods=['POST'])
@login_required
def chat_report():
    """Handle form submission to chat with report."""
    question = request.form.get('chat_question', '').strip()
    
    # Validate input
    if not question:
        session['status_message'] = '⚠️ Please enter a question.'
        return redirect(url_for('index'))
    
    if 'current_report_id' not in session:
        session['status_message'] = '❌ No report available. Please generate a report first.'
        return redirect(url_for('index'))
    
    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)
        agent.current_report_id = session.get('current_report_id')
        
        # Get answer from chat agent
        answer = agent.chat_with_report(question)
        
        # Update chat history in session
        chat_history = session.get('chat_history', [])
        chat_history.append({"role": "user", "content": question})
        chat_history.append({"role": "assistant", "content": answer})
        session['chat_history'] = chat_history
        session['status_message'] = '✅ Answer received'
        
    except Exception as e:
        session['status_message'] = f'❌ Error: {str(e)}'
    
    return redirect(url_for('index'))


@app.route('/clear', methods=['POST'])
@login_required
def clear_conversation():
    """Handle form submission to clear conversation."""
    session['conversation_history'] = []
    session['current_ticker'] = ''
    session['current_trade_type'] = 'Investment'
    session['status_message'] = 'Conversation cleared. Ready for new research.'

    # Optionally reset agent
    session_id = get_or_create_session_id()
    if session_id in agent_sessions:
        try:
            agent_sessions[session_id].reset_conversation()
        except Exception as e:
            app.logger.warning(f"Session reset failed: {e}")

    return redirect(url_for('chat'))


# ==================== Popup Q&A + Background Generation Routes ====================

@app.route('/popup_start', methods=['POST'])
@login_required
def popup_start():
    """Fetch clarifying questions for ticker + trade_type and initialize agent session."""
    ticker = (request.form.get('ticker') or '').strip().upper()
    trade_type = (request.form.get('trade_type') or '').strip()

    if not ticker or not trade_type:
        return jsonify({'error': 'ticker and trade_type are required'}), 400

    session_id = get_or_create_session_id()
    agent = initialize_session(session_id)
    agent.reset_conversation()

    # Set agent state without making an LLM call
    agent.current_ticker = ticker
    agent.current_trade_type = trade_type

    # Store for use in start_generation
    session['current_ticker'] = ticker
    session['current_trade_type'] = trade_type

    questions = _fetch_clarifying_questions(ticker, trade_type)
    return jsonify({'questions': questions, 'session_id': session_id})


@app.route('/start_generation', methods=['POST'])
@login_required
def start_generation():
    """Kick off background report generation with collected Q&A context."""
    data = request.get_json(force=True) or {}
    questions = data.get('questions', [])
    answers = data.get('answers', [])

    session_id = get_or_create_session_id()
    agent = initialize_session(session_id)
    agent.user_id = session.get('user_id')

    # Build context string from Q&A pairs
    lines = []
    for i, q in enumerate(questions):
        a = answers[i] if i < len(answers) else ''
        if q:
            lines.append(f"Q: {q}")
            lines.append(f"A: {a}")
    context_str = "User context:\n" + "\n".join(lines) if lines else ""

    _generation_status[session_id] = {'status': 'in_progress', 'report_id': None}

    ticker = session.get('current_ticker', '')
    trade_type = session.get('current_trade_type', 'Investment')

    def run_generation():
        emitter = create_emitter()
        agent.set_emitter(emitter)
        try:
            agent.generate_report(context=context_str)
            _generation_status[session_id] = {
                'status': 'ready',
                'report_id': agent.current_report_id,
            }
        except Exception as e:
            _generation_status[session_id] = {'status': 'error', 'message': str(e)}
        finally:
            agent.set_emitter(None)

    threading.Thread(target=run_generation, daemon=True).start()
    return jsonify({'success': True})


@app.route('/api/report_status/<session_id>')
@login_required
def report_status(session_id: str):
    """Poll endpoint for background generation status."""
    if session.get('session_id') != session_id:
        return jsonify({'error': 'forbidden'}), 403
    return jsonify(_generation_status.get(session_id, {'status': 'unknown'}))


# ==================== Portfolio Routes ====================

@app.route('/portfolio')
@login_required
def portfolio():
    """Portfolio dashboard."""
    try:
        portfolio_service = get_portfolio_service()
        portfolio_data = portfolio_service.get_default_portfolio(user_id=session['user_id'])
        summary = portfolio_service.get_portfolio_summary(portfolio_data['portfolio_id'])

        # Get status message if any
        status_message = session.pop('status_message', None)

        return render_template(
            'portfolio.html',
            portfolio=portfolio_data,
            summary=summary,
            holdings=summary['holdings'],
            status_message=status_message
        )
    except Exception as e:
        session['status_message'] = f'❌ Error loading portfolio: {str(e)}'
        return render_template(
            'portfolio.html',
            portfolio=None,
            summary=None,
            holdings=[],
            status_message=session.pop('status_message', None)
        )


@app.route('/portfolio/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    """Add transaction form."""
    if request.method == 'POST':
        try:
            portfolio_service = get_portfolio_service()
            portfolio_data = portfolio_service.get_default_portfolio(user_id=session['user_id'])

            # Parse form data
            symbol = request.form.get('symbol', '').strip().upper()
            transaction_type = request.form.get('transaction_type', '')
            quantity = Decimal(request.form.get('quantity', '0'))
            price = Decimal(request.form.get('price', '0'))
            date_str = request.form.get('date', '')
            fees = Decimal(request.form.get('fees', '0') or '0')
            notes = request.form.get('notes', '')
            asset_type = request.form.get('asset_type', None)

            # Validate
            if not symbol:
                raise ValueError("Symbol is required")
            if transaction_type not in ('buy', 'sell'):
                raise ValueError("Invalid transaction type")
            if quantity <= 0:
                raise ValueError("Quantity must be positive")
            if price <= 0:
                raise ValueError("Price must be positive")
            if not date_str:
                raise ValueError("Date is required")

            transaction_date = datetime.strptime(date_str, '%Y-%m-%d')

            # Add transaction
            portfolio_service.add_transaction(
                portfolio_id=portfolio_data['portfolio_id'],
                symbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                price_per_unit=price,
                transaction_date=transaction_date,
                fees=fees,
                notes=notes,
                asset_type=asset_type if asset_type else None,
            )

            session['status_message'] = f'✅ Transaction added: {transaction_type.upper()} {quantity} {symbol}'

        except Exception as e:
            session['status_message'] = f'❌ Error: {str(e)}'

        return redirect(url_for('portfolio'))

    # GET request - show form
    status_message = session.pop('status_message', None)
    return render_template('add_transaction.html', status_message=status_message)


@app.route('/portfolio/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    """CSV import page."""
    if request.method == 'POST':
        try:
            portfolio_service = get_portfolio_service()
            portfolio_data = portfolio_service.get_default_portfolio(user_id=session['user_id'])

            if 'csv_file' not in request.files:
                raise ValueError("No file uploaded")

            file = request.files['csv_file']
            if file.filename == '':
                raise ValueError("No file selected")

            file.seek(0, 2)
            if file.tell() > 10 * 1024 * 1024:
                raise ValueError("File exceeds 10MB limit")
            file.seek(0)
            csv_content = file.read().decode('utf-8')
            result = portfolio_service.import_csv(
                portfolio_id=portfolio_data['portfolio_id'],
                csv_content=csv_content,
                filename=file.filename
            )

            if result.error_count > 0:
                session['status_message'] = f'⚠️ Imported {result.success_count} transactions, {result.error_count} errors'
                session['import_errors'] = result.errors[:10]  # Limit to first 10 errors
            else:
                session['status_message'] = f'✅ Successfully imported {result.success_count} transactions'

        except Exception as e:
            session['status_message'] = f'❌ Import failed: {str(e)}'

        return redirect(url_for('portfolio'))

    # GET request - show import form
    status_message = session.pop('status_message', None)
    import_errors = session.pop('import_errors', None)
    return render_template('import_csv.html', status_message=status_message, import_errors=import_errors)


@app.route('/portfolio/holding/<symbol>')
@login_required
def holding_detail(symbol: str):
    """View holding details and transactions."""
    try:
        portfolio_service = get_portfolio_service()
        portfolio_data = portfolio_service.get_default_portfolio(user_id=session['user_id'])
        holding = portfolio_service.get_holding(portfolio_data['portfolio_id'], symbol)

        if not holding:
            session['status_message'] = f'⚠️ Holding not found: {symbol}'
            return redirect(url_for('portfolio'))

        if holding.get('total_quantity', Decimal('0')) <= Decimal('0'):
            session['status_message'] = f'⚠️ {symbol} is a closed position with no remaining quantity.'
            return redirect(url_for('portfolio'))

        transactions = portfolio_service.get_transactions(holding['holding_id'])

        # Get current price
        provider, _ = DataProviderFactory.get_provider_for_symbol(symbol)
        current_price = provider.get_current_price(symbol) or Decimal('0')

        holding['current_price'] = current_price
        holding['market_value'] = holding['total_quantity'] * current_price
        holding['unrealized_gain'] = holding['market_value'] - holding['total_cost_basis']

        if holding['total_cost_basis'] > 0:
            holding['unrealized_gain_pct'] = (holding['unrealized_gain'] / holding['total_cost_basis']) * 100
        else:
            holding['unrealized_gain_pct'] = Decimal('0')

        status_message = session.pop('status_message', None)

        return render_template(
            'holding_detail.html',
            holding=holding,
            transactions=transactions,
            status_message=status_message
        )

    except Exception as e:
        session['status_message'] = f'❌ Error: {str(e)}'
        return redirect(url_for('portfolio'))


@app.route('/portfolio/transaction/<transaction_id>/delete', methods=['POST'])
@login_required
def delete_transaction(transaction_id: str):
    """Delete a transaction."""
    try:
        portfolio_service = get_portfolio_service()

        txn = portfolio_service.get_transaction(transaction_id)
        if not txn:
            session['status_message'] = '❌ Transaction not found'
            return redirect(url_for('portfolio'))

        holding = portfolio_service.get_holding_by_id(txn['holding_id'])
        if not holding:
            session['status_message'] = '❌ Transaction not found'
            return redirect(url_for('portfolio'))

        portfolio = portfolio_service.get_portfolio(holding['portfolio_id'])
        if not portfolio or portfolio.get('user_id') != session['user_id']:
            session['status_message'] = '❌ Not authorized'
            return redirect(url_for('portfolio'))

        symbol = holding['symbol']
        if portfolio_service.delete_transaction(transaction_id):
            session['status_message'] = '✅ Transaction deleted'
        else:
            session['status_message'] = '❌ Failed to delete transaction'
        return redirect(url_for('holding_detail', symbol=symbol))

    except Exception as e:
        session['status_message'] = f'❌ Error: {str(e)}'

    return redirect(url_for('portfolio'))


@app.route('/api/portfolio/<portfolio_id>/history')
@login_required
def portfolio_history(portfolio_id):
    """Return monthly portfolio value history as JSON."""
    portfolio = get_portfolio_service().get_portfolio(portfolio_id)
    if not portfolio or portfolio.get('user_id') != session['user_id']:
        return jsonify({'error': 'Not found'}), 404
    history_service = get_history_service()
    data = history_service.get_monthly_values(portfolio_id)
    return jsonify(data)


# ============================================================================
# Report History & Export Routes
# ============================================================================
@app.route('/reports')
@login_required
def report_history():
    """Render the report history page with filters."""
    get_or_create_session_id()

    # Get filter parameters from query string
    ticker = request.args.get('ticker', '').strip().upper() or None
    trade_type = request.args.get('trade_type', '').strip() or None
    sort_order = request.args.get('sort', 'DESC').upper()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 12

    # Calculate offset
    offset = (page - 1) * per_page

    try:
        storage = ReportStorage()
        user_id = session.get('user_id')
        reports, total_count = storage.get_all_reports(
            ticker=ticker,
            trade_type=trade_type,
            sort_order=sort_order,
            limit=per_page,
            offset=offset,
            user_id=user_id
        )

        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        return render_template(
            'reports.html',
            reports=reports,
            total_count=total_count,
            current_page=page,
            total_pages=total_pages,
            per_page=per_page,
            filter_ticker=ticker or '',
            filter_trade_type=trade_type or '',
            sort_order=sort_order,
            page_range=_page_range(page, total_pages)
        )
    except Exception as e:
        return render_template(
            'reports.html',
            reports=[],
            total_count=0,
            current_page=1,
            total_pages=1,
            per_page=per_page,
            filter_ticker='',
            filter_trade_type='',
            sort_order='DESC',
            page_range=[1],
            error=str(e)
        )


@app.route('/api/news')
def api_news():
    from news_service import get_briefing
    return jsonify(get_briefing())


@app.route('/api/news/more')
def api_news_more():
    from news_service import get_more
    return jsonify(get_more())


@app.route('/api/reports')
@login_required
def api_reports():
    """AJAX endpoint for filtered reports (returns JSON)."""
    ticker = request.args.get('ticker', '').strip().upper() or None
    trade_type = request.args.get('trade_type', '').strip() or None
    sort_order = request.args.get('sort', 'DESC').upper()
    try:
        page = max(1, int(request.args.get('page', 1)))
    except (ValueError, TypeError):
        page = 1
    per_page = 12

    offset = (page - 1) * per_page

    try:
        storage = ReportStorage()
        user_id = session.get('user_id')
        reports, total_count = storage.get_all_reports(
            ticker=ticker,
            trade_type=trade_type,
            sort_order=sort_order,
            limit=per_page,
            offset=offset,
            user_id=user_id
        )

        # Convert datetime objects to ISO strings for JSON
        for report in reports:
            if report.get('created_at'):
                report['created_at'] = report['created_at'].isoformat()

        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 1

        return jsonify({
            'success': True,
            'reports': reports,
            'total_count': total_count,
            'current_page': page,
            'total_pages': total_pages
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/report/<report_id>')
@login_required
def view_report(report_id):
    """View a single report."""
    try:
        storage = ReportStorage()
        report = storage.get_report(report_id, user_id=session.get('user_id'))

        if not report:
            abort(404)

        return render_template(
            'report_view.html',
            report=report
        )
    except Exception as e:
        app.logger.error(f"Error loading report {report_id}: {e}")
        abort(500)


@app.route('/report/<report_id>/pdf')
@login_required
def download_report_pdf(report_id):
    """Download report as PDF."""
    try:
        storage = ReportStorage()
        report = storage.get_report(report_id, user_id=session.get('user_id'))

        if not report:
            abort(404)

        # Generate PDF
        pdf_generator = get_pdf_generator()
        pdf_bytes = pdf_generator.generate_pdf(
            ticker=report['ticker'],
            trade_type=report['trade_type'],
            report_text=report['report_text'],
            created_at=report.get('created_at')
        )

        # Create filename
        filename = f"{report['ticker']}_report_{report_id[:8]}.pdf"

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': len(pdf_bytes)
            }
        )
    except Exception as e:
        app.logger.error(f"Error generating PDF for report {report_id}: {e}")
        abort(500)


@app.route('/report/<report_id>/chat')
@login_required
def chat_with_report(report_id):
    """Open chat interface with report context pre-loaded."""
    try:
        storage = ReportStorage()
        report = storage.get_report(report_id, user_id=session.get('user_id'))

        if not report:
            abort(404)

        # Store report context in session for chat
        session['current_report_id'] = report_id
        session['current_ticker'] = report['ticker']
        session['current_trade_type'] = report['trade_type']

        # Initialize conversation with report context
        session['conversation_history'] = [
            {
                "role": "assistant",
                "content": f"I've loaded the research report for **{report['ticker']}** ({report['trade_type']}). "
                           f"Feel free to ask me any questions about this analysis!"
            }
        ]
        session['status_message'] = f'Report loaded: {report["ticker"]}'

        return redirect(url_for('chat'))
    except Exception as e:
        session['status_message'] = f'Error loading report: {str(e)}'
        return redirect(url_for('report_history'))


# ==================== Watchlist Routes ====================

@app.route('/watchlist')
@login_required
def watchlist():
    """Main watchlist page — auto-creates default watchlist if none exist."""
    try:
        watchlist_svc = get_watchlist_service()
        user_id = session['user_id']
        watchlists = watchlist_svc.list_watchlists(user_id)

        # Auto-create default
        if not watchlists:
            watchlist_svc.get_or_create_default_watchlist(user_id)
            watchlists = watchlist_svc.list_watchlists(user_id)

        active_watchlist_id = request.args.get('wl', watchlists[0]['watchlist_id'] if watchlists else None)
        active_watchlist = None
        if active_watchlist_id:
            # Ownership check
            wl = watchlist_svc.db.get_watchlist(active_watchlist_id)
            if wl and wl['user_id'] == user_id:
                active_watchlist = watchlist_svc.get_watchlist_with_items(active_watchlist_id)

        status_message = session.pop('status_message', None)
        return render_template(
            'watchlist.html',
            watchlists=watchlists,
            active_watchlist=active_watchlist,
            status_message=status_message
        )
    except Exception as e:
        return render_template(
            'watchlist.html',
            watchlists=[],
            active_watchlist=None,
            status_message=f'Error loading watchlist: {str(e)}'
        )


@app.route('/watchlist/create', methods=['POST'])
@login_required
def watchlist_create():
    name = request.form.get('name', '').strip() or 'My Watchlist'
    try:
        watchlist_svc = get_watchlist_service()
        wl_id = watchlist_svc.create_watchlist(session['user_id'], name)
        session['status_message'] = f'Watchlist "{name}" created'
        return redirect(url_for('watchlist', wl=wl_id))
    except Exception as e:
        session['status_message'] = f'Error: {str(e)}'
        return redirect(url_for('watchlist'))


@app.route('/watchlist/<watchlist_id>/rename', methods=['POST'])
@login_required
def watchlist_rename(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl['user_id'] != session['user_id']:
        abort(403)
    name = request.form.get('name', '').strip()
    if name:
        watchlist_svc.rename_watchlist(watchlist_id, name)
        session['status_message'] = f'Renamed to "{name}"'
    return redirect(url_for('watchlist', wl=watchlist_id))


@app.route('/watchlist/<watchlist_id>/delete', methods=['POST'])
@login_required
def watchlist_delete(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl['user_id'] != session['user_id']:
        abort(403)
    watchlist_svc.delete_watchlist(watchlist_id)
    session['status_message'] = 'Watchlist deleted'
    return redirect(url_for('watchlist'))


@app.route('/watchlist/<watchlist_id>/add-symbol', methods=['POST'])
@login_required
def watchlist_add_symbol(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl['user_id'] != session['user_id']:
        abort(403)
    symbol = request.form.get('symbol', '').strip().upper()
    section_id = request.form.get('section_id') or None
    if not symbol:
        session['status_message'] = 'Symbol is required'
        return redirect(url_for('watchlist', wl=watchlist_id))
    try:
        watchlist_svc.add_symbol(watchlist_id, symbol, section_id)
        session['status_message'] = f'{symbol} added to watchlist'
    except ValueError as e:
        session['status_message'] = str(e)
    except Exception as e:
        session['status_message'] = f'Error adding {symbol}: {str(e)}'
    return redirect(url_for('watchlist', wl=watchlist_id))


@app.route('/watchlist/item/<item_id>/remove', methods=['POST'])
@login_required
def watchlist_remove_item(item_id):
    watchlist_svc = get_watchlist_service()
    # Find which watchlist this item belongs to for ownership check + redirect
    from database import get_database_manager
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT wi.watchlist_id, wl.user_id
                FROM watchlist_items wi
                JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                WHERE wi.item_id = %s
            """, (item_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or row['user_id'] != session['user_id']:
        abort(403)

    watchlist_id = row['watchlist_id']
    watchlist_svc.remove_symbol(item_id)
    session['status_message'] = 'Symbol removed'
    return redirect(url_for('watchlist', wl=watchlist_id))


@app.route('/watchlist/item/<item_id>/pin', methods=['POST'])
@login_required
def watchlist_toggle_pin(item_id):
    watchlist_svc = get_watchlist_service()
    from database import get_database_manager
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT wi.watchlist_id, wi.is_pinned, wl.user_id
                FROM watchlist_items wi
                JOIN watchlists wl ON wi.watchlist_id = wl.watchlist_id
                WHERE wi.item_id = %s
            """, (item_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or row['user_id'] != session['user_id']:
        abort(403)

    watchlist_id = row['watchlist_id']
    user_id = session['user_id']

    try:
        if row['is_pinned']:
            watchlist_svc.unpin_item(item_id)
            session['status_message'] = 'Unpinned from homepage'
        else:
            watchlist_svc.pin_item(user_id, item_id)
            session['status_message'] = 'Pinned to homepage'
    except ValueError as e:
        session['status_message'] = str(e)

    return redirect(url_for('watchlist', wl=watchlist_id))


@app.route('/watchlist/<watchlist_id>/section/create', methods=['POST'])
@login_required
def watchlist_create_section(watchlist_id):
    watchlist_svc = get_watchlist_service()
    wl = watchlist_svc.db.get_watchlist(watchlist_id)
    if not wl or wl['user_id'] != session['user_id']:
        abort(403)
    name = request.form.get('name', '').strip()
    if name:
        try:
            watchlist_svc.create_section(watchlist_id, name)
            session['status_message'] = f'Section "{name}" created'
        except Exception as e:
            session['status_message'] = f'Error creating section: {str(e)}'
    return redirect(url_for('watchlist', wl=watchlist_id))


@app.route('/watchlist/section/<section_id>/rename', methods=['POST'])
@login_required
def watchlist_rename_section(section_id):
    watchlist_svc = get_watchlist_service()
    from database import get_database_manager
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT ws.watchlist_id, wl.user_id
                FROM watchlist_sections ws
                JOIN watchlists wl ON ws.watchlist_id = wl.watchlist_id
                WHERE ws.section_id = %s
            """, (section_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or row['user_id'] != session['user_id']:
        abort(403)

    name = request.form.get('name', '').strip()
    if name:
        watchlist_svc.rename_section(section_id, name)
        session['status_message'] = f'Section renamed to "{name}"'
    return redirect(url_for('watchlist', wl=row['watchlist_id']))


@app.route('/watchlist/section/<section_id>/delete', methods=['POST'])
@login_required
def watchlist_delete_section(section_id):
    watchlist_svc = get_watchlist_service()
    from database import get_database_manager
    db = get_database_manager()
    conn = db.get_connection()
    try:
        with conn.cursor(dictionary=True) as cur:
            cur.execute("""
                SELECT ws.watchlist_id, wl.user_id
                FROM watchlist_sections ws
                JOIN watchlists wl ON ws.watchlist_id = wl.watchlist_id
                WHERE ws.section_id = %s
            """, (section_id,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or row['user_id'] != session['user_id']:
        abort(403)

    watchlist_svc.delete_section(section_id)
    session['status_message'] = 'Section deleted'
    return redirect(url_for('watchlist', wl=row['watchlist_id']))


def main():
    """Main entry point for the Flask app."""
    # Check for required environment variables
    if not os.getenv("GEMINI_API_KEY"):
        print("Warning: GEMINI_API_KEY not found in environment variables.")
        print("Please set it in your .env file or environment.")

    from watchlist.price_refresh import start_price_refresh
    start_price_refresh()

    app.run(
        host='127.0.0.1',
        port=int(os.getenv('PORT', 5000)),
        debug=True
    )


if __name__ == "__main__":
    main()

