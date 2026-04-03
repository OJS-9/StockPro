"""
Tests for multiple portfolio support routes.
Covers: portfolio list, portfolio create, portfolio detail with portfolio_id-scoped URLs.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).parent / 'src'))


@pytest.fixture
def app():
    """Create a Flask test app."""
    from app import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    flask_app.config['SECRET_KEY'] = 'test-secret'
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def logged_in_client(client):
    """Client with a logged-in session."""
    with client.session_transaction() as sess:
        sess['user_id'] = 'user-1'
        sess['username'] = 'testuser'
    return client


def make_portfolio(portfolio_id='p-1', name='My Portfolio', user_id='user-1'):
    return {
        'portfolio_id': portfolio_id,
        'name': name,
        'user_id': user_id,
        'description': '',
    }


def make_summary():
    return {
        'portfolio_id': 'p-1',
        'total_market_value': Decimal('1000.00'),
        'total_cost_basis': Decimal('900.00'),
        'total_unrealized_gain': Decimal('100.00'),
        'total_unrealized_gain_pct': Decimal('11.11'),
        'stock_allocation_pct': Decimal('100.00'),
        'crypto_allocation_pct': Decimal('0.00'),
        'holdings_count': 1,
        'holdings': [],
    }


def make_list_response(portfolios, overall=None):
    """Return shape of get_portfolios_with_summaries for list page tests."""
    return {'portfolios': portfolios, 'overall': overall}


class TestPortfolioList:
    """GET /portfolio shows portfolio list page."""

    def test_portfolio_list_redirects_if_not_logged_in(self, client):
        """Unauthenticated access redirects to login."""
        response = client.get('/portfolio')
        assert response.status_code == 302
        assert '/sign-in' in response.headers['Location']

    def test_portfolio_list_renders_for_logged_in_user(self, logged_in_client):
        """Logged-in user sees portfolio list page."""
        p = make_portfolio()
        p['summary'] = {
            'total_market_value': Decimal('1000.00'),
            'total_cost_basis': Decimal('900.00'),
            'total_unrealized_gain': Decimal('100.00'),
            'total_unrealized_gain_pct': Decimal('11.11'),
            'holdings_count': 1,
        }
        overall = {
            'total_market_value': Decimal('1000.00'),
            'total_cost_basis': Decimal('900.00'),
            'total_unrealized_gain': Decimal('100.00'),
            'total_unrealized_gain_pct': Decimal('11.11'),
            'total_holdings_count': 1,
        }
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolios_with_summaries.return_value = make_list_response([p], overall)
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio')
            assert response.status_code == 200
            assert b'My Portfolio' in response.data

    def test_portfolio_list_shows_empty_state(self, logged_in_client):
        """Empty portfolio list shows create portfolio button."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolios_with_summaries.return_value = make_list_response([], overall=None)
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio')
            assert response.status_code == 200
            assert b'Create Portfolio' in response.data

    def test_portfolio_list_shows_multiple_portfolios(self, logged_in_client):
        """Multiple portfolios all appear on list page."""
        p1 = make_portfolio('p-1', 'Tech Portfolio')
        p1['summary'] = {'total_market_value': Decimal('500.00'), 'total_cost_basis': Decimal('400.00'),
                         'total_unrealized_gain': Decimal('100.00'), 'total_unrealized_gain_pct': Decimal('25.0'),
                         'holdings_count': 2}
        p2 = make_portfolio('p-2', 'Crypto Portfolio')
        p2['summary'] = {'total_market_value': Decimal('1500.00'), 'total_cost_basis': Decimal('1200.00'),
                         'total_unrealized_gain': Decimal('300.00'), 'total_unrealized_gain_pct': Decimal('25.0'),
                         'holdings_count': 1}
        overall = {
            'total_market_value': Decimal('2000.00'),
            'total_cost_basis': Decimal('1600.00'),
            'total_unrealized_gain': Decimal('400.00'),
            'total_unrealized_gain_pct': Decimal('25.0'),
            'total_holdings_count': 3,
        }
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolios_with_summaries.return_value = make_list_response([p1, p2], overall)
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio')
            assert response.status_code == 200
            assert b'Tech Portfolio' in response.data
            assert b'Crypto Portfolio' in response.data

    def test_portfolio_list_includes_recap_when_portfolios_exist(self, logged_in_client):
        """List page shows overall recap (total value, P&L %, total holdings) when user has portfolios."""
        p = make_portfolio('p-1', 'My Portfolio')
        p['summary'] = {
            'total_market_value': Decimal('10000.50'),
            'total_cost_basis': Decimal('9000.00'),
            'total_unrealized_gain': Decimal('1000.50'),
            'total_unrealized_gain_pct': Decimal('11.12'),
            'holdings_count': 5,
        }
        overall = {
            'total_market_value': Decimal('10000.50'),
            'total_cost_basis': Decimal('9000.00'),
            'total_unrealized_gain': Decimal('1000.50'),
            'total_unrealized_gain_pct': Decimal('11.12'),
            'total_holdings_count': 5,
        }
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolios_with_summaries.return_value = make_list_response([p], overall)
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio')
            assert response.status_code == 200
            assert b'Total Value' in response.data
            assert b'Unrealized P&L' in response.data
            # Overall recap strip shows cost basis (currency-filtered)
            assert b'9,000.00' in response.data or b'9000.00' in response.data
            assert b'Total Holdings' in response.data
            assert b'5' in response.data
            assert b'holding' in response.data.lower()


class TestCreatePortfolio:
    """POST /portfolio/create creates a new portfolio."""

    def test_create_portfolio_redirects_if_not_logged_in(self, client):
        response = client.post('/portfolio/create', data={'name': 'Test'})
        assert response.status_code == 302
        assert '/sign-in' in response.headers['Location']

    def test_create_portfolio_redirects_to_detail(self, logged_in_client):
        """POST /portfolio/create redirects to /portfolio/<id>."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.create_portfolio.return_value = 'new-portfolio-id'
            mock_svc.return_value = svc

            response = logged_in_client.post('/portfolio/create', data={'name': 'My New Portfolio'})
            assert response.status_code == 302
            assert '/portfolio/new-portfolio-id' in response.headers['Location']

    def test_create_portfolio_empty_name_redirects_to_list(self, logged_in_client):
        """POST /portfolio/create with empty name redirects back to list."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            mock_svc.return_value = svc

            response = logged_in_client.post('/portfolio/create', data={'name': ''})
            assert response.status_code == 302
            # Should redirect to portfolio list
            assert response.headers['Location'].endswith('/portfolio') or '/portfolio' in response.headers['Location']


class TestPortfolioDetail:
    """GET /portfolio/<portfolio_id> shows portfolio dashboard."""

    def test_portfolio_detail_redirects_if_not_logged_in(self, client):
        response = client.get('/portfolio/p-1')
        assert response.status_code == 302
        assert '/sign-in' in response.headers['Location']

    def test_portfolio_detail_shows_404_for_wrong_user(self, logged_in_client):
        """Portfolio belonging to different user returns 404."""
        other_user_portfolio = make_portfolio('p-1', user_id='other-user')
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = other_user_portfolio
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1')
            assert response.status_code == 404

    def test_portfolio_detail_shows_dashboard(self, logged_in_client):
        """Portfolio detail page renders with summary data."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio()
            svc.get_portfolio_summary.return_value = make_summary()
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1')
            assert response.status_code == 200

    def test_portfolio_detail_shows_404_for_nonexistent(self, logged_in_client):
        """Non-existent portfolio returns 404."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = None
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/nonexistent')
            assert response.status_code == 404


class TestAddTransactionScoped:
    """GET/POST /portfolio/<id>/add scoped to specific portfolio."""

    def test_add_transaction_url_includes_portfolio_id(self, logged_in_client):
        """GET /portfolio/<id>/add renders form."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio()
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1/add')
            assert response.status_code == 200

    def test_add_transaction_wrong_user_returns_404(self, logged_in_client):
        """GET /portfolio/<id>/add for other user's portfolio returns 404."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio('p-1', user_id='other-user')
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1/add')
            assert response.status_code == 404

    def test_post_add_transaction_redirects_to_portfolio_detail(self, logged_in_client):
        """POST /portfolio/<id>/add redirects to /portfolio/<id>."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio()
            svc.add_transaction.return_value = None
            mock_svc.return_value = svc

            response = logged_in_client.post('/portfolio/p-1/add', data={
                'symbol': 'AAPL',
                'transaction_type': 'buy',
                'quantity': '10',
                'price': '150.00',
                'date': '2024-01-15',
                'fees': '0',
                'notes': '',
                'asset_type': '',
            })
            assert response.status_code == 302
            assert '/portfolio/p-1' in response.headers['Location']


class TestImportCSVScoped:
    """GET/POST /portfolio/<id>/import scoped to specific portfolio."""

    def test_import_csv_url_includes_portfolio_id(self, logged_in_client):
        """GET /portfolio/<id>/import renders form."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio()
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1/import')
            assert response.status_code == 200

    def test_import_csv_wrong_user_returns_404(self, logged_in_client):
        """GET /portfolio/<id>/import for other user's portfolio returns 404."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio('p-1', user_id='other-user')
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1/import')
            assert response.status_code == 404


class TestHoldingDetailScoped:
    """GET /portfolio/<id>/holding/<symbol> scoped to specific portfolio."""

    def test_holding_detail_url_includes_portfolio_id(self, logged_in_client):
        """GET /portfolio/<id>/holding/<symbol> renders detail."""
        holding = {
            'holding_id': 'h-1',
            'symbol': 'AAPL',
            'asset_type': 'stock',
            'total_quantity': Decimal('10'),
            'average_cost': Decimal('150.00'),
            'total_cost_basis': Decimal('1500.00'),
            'portfolio_id': 'p-1',
        }
        with patch('app.get_portfolio_service') as mock_svc, \
             patch('app.DataProviderFactory') as mock_factory:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio()
            svc.get_holding.return_value = holding
            svc.get_transactions.return_value = []
            mock_svc.return_value = svc

            provider = MagicMock()
            provider.get_current_price.return_value = Decimal('160.00')
            mock_factory.get_provider_for_symbol.return_value = (provider, 'stock')

            response = logged_in_client.get('/portfolio/p-1/holding/AAPL')
            assert response.status_code == 200

    def test_holding_detail_wrong_user_returns_404(self, logged_in_client):
        """GET /portfolio/<id>/holding/<symbol> for other user's portfolio returns 404."""
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_portfolio.return_value = make_portfolio('p-1', user_id='other-user')
            mock_svc.return_value = svc

            response = logged_in_client.get('/portfolio/p-1/holding/AAPL')
            assert response.status_code == 404


class TestDeleteTransactionScoped:
    """POST /portfolio/<id>/transaction/<txn_id>/delete."""

    def test_delete_transaction_url_includes_portfolio_id(self, logged_in_client):
        """POST /portfolio/<id>/transaction/<txn_id>/delete redirects to portfolio detail."""
        holding = {'holding_id': 'h-1', 'symbol': 'AAPL', 'portfolio_id': 'p-1'}
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_transaction.return_value = {'transaction_id': 'txn-1', 'holding_id': 'h-1'}
            svc.get_holding_by_id.return_value = holding
            svc.get_portfolio.return_value = make_portfolio()
            svc.delete_transaction.return_value = True
            mock_svc.return_value = svc

            response = logged_in_client.post('/portfolio/p-1/transaction/txn-1/delete')
            assert response.status_code == 302
            assert '/portfolio/p-1' in response.headers['Location']

    def test_delete_transaction_wrong_owner_does_not_delete(self, logged_in_client):
        """Cannot delete a transaction on another user's portfolio."""
        holding = {'holding_id': 'h-1', 'symbol': 'AAPL', 'portfolio_id': 'p-1'}
        with patch('app.get_portfolio_service') as mock_svc:
            svc = MagicMock()
            svc.get_transaction.return_value = {'transaction_id': 'txn-1', 'holding_id': 'h-1'}
            svc.get_holding_by_id.return_value = holding
            svc.get_portfolio.return_value = make_portfolio('p-1', user_id='other-user')
            mock_svc.return_value = svc

            response = logged_in_client.post('/portfolio/p-1/transaction/txn-1/delete')
            assert response.status_code == 302
            assert response.headers['Location'].endswith('/portfolio')
            svc.delete_transaction.assert_not_called()
