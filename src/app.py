"""
Flask web interface for the Stock Research AI Agent.
"""

import sys
from pathlib import Path

# Add project root to Python path to allow imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import os
from dotenv import load_dotenv
import uuid
import markdown
from decimal import Decimal
from datetime import datetime

from agent import create_agent, StockResearchAgent
from portfolio.portfolio_service import get_portfolio_service
from data_providers import DataProviderFactory

# Load environment variables
load_dotenv()

# Create Flask app
# Set template and static folders explicitly to point to project root
app = Flask(__name__, 
            template_folder=str(project_root / 'templates'), 
            static_folder=str(project_root / 'static'))
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())

# Register markdown filter for Jinja2 templates
app.jinja_env.filters['markdown'] = markdown.markdown

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


@app.route('/')
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
def portfolio():
    """Portfolio dashboard."""
    try:
        portfolio_service = get_portfolio_service()
        portfolio_data = portfolio_service.get_default_portfolio()
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
def add_transaction():
    """Add transaction form."""
    if request.method == 'POST':
        try:
            portfolio_service = get_portfolio_service()
            portfolio_data = portfolio_service.get_default_portfolio()

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
def import_csv():
    """CSV import page."""
    if request.method == 'POST':
        try:
            portfolio_service = get_portfolio_service()
            portfolio_data = portfolio_service.get_default_portfolio()

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
def holding_detail(symbol: str):
    """View holding details and transactions."""
    try:
        portfolio_service = get_portfolio_service()
        portfolio_data = portfolio_service.get_default_portfolio()
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


def main():
    """Main entry point for the Flask app."""
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not found in environment variables.")
        print("Please set it in your .env file or environment.")
    
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True
    )


if __name__ == "__main__":
    main()

