"""
Flask web interface for the Stock Research AI Agent.
"""

import sys
from pathlib import Path

# Add project root to Python path to allow imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, abort
import os
import re
from functools import wraps
from dotenv import load_dotenv
import uuid
import markdown as md_lib
from markupsafe import Markup
from decimal import Decimal
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

from agent import create_agent, StockResearchAgent
from portfolio.portfolio_service import get_portfolio_service
from data_providers import DataProviderFactory
from report_storage import ReportStorage
from pdf_generator import get_pdf_generator

# Load environment variables
load_dotenv()

# Create Flask app
# Set template and static folders explicitly to point to project root
app = Flask(__name__, 
            template_folder=str(project_root / 'templates'), 
            static_folder=str(project_root / 'static'))
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            session['next_url'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_user():
    return {'current_user': {
        'is_authenticated': 'user_id' in session,
        'user_id': session.get('user_id'),
        'username': session.get('username'),
    }}



@app.template_filter('markdown')
def markdown_filter(text):
    return Markup(md_lib.markdown(
        text or '',
        extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
    ))


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


def initialize_session(session_id: str) -> StockResearchAgent:
    """
    Initialize or get agent for a session.
    
    Args:
        session_id: Unique session identifier
    
    Returns:
        StockResearchAgent instance
    """
    if session_id not in agent_sessions:
        try:
            agent_sessions[session_id] = create_agent()
        except Exception as e:
            raise ValueError(f"Failed to initialize agent: {str(e)}")
    return agent_sessions[session_id]


def get_or_create_session_id():
    """Get or create a session ID for the current user."""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            session['next_url'] = request.url
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ==================== Auth Routes ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            error = 'Username and password are required.'
        else:
            from database import get_database_manager
            db = get_database_manager()
            user = db.get_user_by_username(username)

            if user and check_password_hash(user['password_hash'], password):
                next_url = session.get('next_url')
                session.clear()
                session['user_id'] = user['user_id']
                session['username'] = user['username']
                get_or_create_session_id()
                return redirect(next_url or url_for('index'))
            else:
                error = 'Invalid username or password.'

    return render_template('login.html', error=error)


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Registration page."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(password) < 8:
            error = 'Password must be at least 8 characters.'
        elif password != confirm_password:
            error = 'Passwords do not match.'
        elif not email:
            error = 'Email is required.'
        else:
            try:
                from database import get_database_manager
                db = get_database_manager()
                user_id = str(uuid.uuid4())
                password_hash = generate_password_hash(password)
                db.create_user(user_id, username, email, password_hash)

                session.clear()
                session['user_id'] = user_id
                session['username'] = username
                get_or_create_session_id()
                return redirect(url_for('index'))
            except RuntimeError as e:
                if 'Duplicate entry' in str(e):
                    error = 'Username or email already taken.'
                else:
                    error = f'Registration failed: {str(e)}'

    return render_template('register.html', error=error)


@app.route('/logout')
def logout():
    """Log out and redirect to login."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def index():
    """Render the main landing page."""
    # Initialize session ID if needed
    get_or_create_session_id()
    
    # Get current values from session for form pre-filling
    current_ticker = session.get('current_ticker', '')
    current_trade_type = session.get('current_trade_type', 'Investment')
    
    return render_template(
        'index.html',
        current_ticker=current_ticker,
        current_trade_type=current_trade_type
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
    """Handle form submission to continue conversation."""
    user_input = request.form.get('user_response', '').strip()
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Validate input
    if not user_input:
        if is_ajax:
            return jsonify({'success': False, 'error': '⚠️ Please enter a response.'}), 400
        session['status_message'] = '⚠️ Please enter a response.'
        return redirect(url_for('chat'))
    
    try:
        session_id = get_or_create_session_id()
        agent = initialize_session(session_id)
        agent.user_id = session.get('user_id')

        # Store previous report_id to detect if a new report was generated
        previous_report_id = session.get('current_report_id')

        # Get agent response
        response = agent.continue_conversation(user_input)
        
        # Get current conversation history
        conversation_history = session.get('conversation_history', [])
        
        # Append user message and agent response
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": response})
        
        # Check if a report was generated during this conversation turn
        current_report_id = agent.current_report_id
        report_generated = False
        report_preview = None
        
        if current_report_id and current_report_id != previous_report_id:
            # A new report was generated - get full report text from agent and add to conversation
            report_text = getattr(agent, 'last_report_text', None) or session.get('report_text', '')
            if report_text:
                # Display the full report text in the chat
                report_preview = f"# Research Report\n\n{report_text}"
                conversation_history.append({
                    "role": "assistant",
                    "content": report_preview
                })
                session['current_report_id'] = current_report_id
                session['report_text'] = report_text
                report_generated = True
        
        # Update session
        session['conversation_history'] = conversation_history
        session['status_message'] = '✅ Response received'
        
        # If AJAX request, return JSON
        if is_ajax:
            return jsonify({
                'success': True,
                'user_message': user_input,
                'assistant_message': response,
                'conversation_history': conversation_history,
                'report_generated': report_generated,
                'report_preview': report_preview
            })
        
    except Exception as e:
        if is_ajax:
            return jsonify({'success': False, 'error': f'❌ Error: {str(e)}'}), 500
        session['status_message'] = f'❌ Error: {str(e)}'
    
    return redirect(url_for('chat'))


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
        except:
            pass

    return redirect(url_for('chat'))


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

        # Get transaction to find symbol for redirect
        txn = portfolio_service.get_transaction(transaction_id)
        if not txn:
            session['status_message'] = '❌ Transaction not found'
            return redirect(url_for('portfolio'))

        holding = portfolio_service.get_holding_by_id(txn['holding_id'])
        symbol = holding['symbol'] if holding else None

        if portfolio_service.delete_transaction(transaction_id):
            session['status_message'] = '✅ Transaction deleted'
        else:
            session['status_message'] = '❌ Failed to delete transaction'

        # Redirect back to holding detail if we have the symbol
        if symbol:
            return redirect(url_for('holding_detail', symbol=symbol))

    except Exception as e:
        session['status_message'] = f'❌ Error: {str(e)}'

    return redirect(url_for('portfolio'))


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


def main():
    """Main entry point for the Flask app."""
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not found in environment variables.")
        print("Please set it in your .env file or environment.")
    
    app.run(
        host='127.0.0.1',
        port=int(os.getenv('PORT', 5000)),
        debug=True
    )


if __name__ == "__main__":
    main()

