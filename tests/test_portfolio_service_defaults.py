from unittest.mock import MagicMock

from portfolio.portfolio_service import PortfolioService


def test_create_portfolio_defaults_track_cash_true():
    service = PortfolioService()
    service._db = MagicMock()
    service._db.create_portfolio.return_value = None

    service.create_portfolio(name="Default Cash", user_id="user-1")

    service._db.create_portfolio.assert_called_once()
    assert service._db.create_portfolio.call_args.kwargs["track_cash"] is True
    assert service._db.create_portfolio.call_args.kwargs["cash_balance"] == 0.0
