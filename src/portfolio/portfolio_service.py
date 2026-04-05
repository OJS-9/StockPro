"""
Portfolio service - main business logic for portfolio operations.
"""

import uuid
import sys
import os
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .cost_basis import calculate_simple_average
from .csv_importer import CSVImporter, ImportResult


class PortfolioService:
    """Main service for portfolio operations."""

    def __init__(self):
        """Initialize portfolio service."""
        self._db = None
        self._provider_factory = None
        self.csv_importer = CSVImporter()

    @property
    def db(self):
        """Lazy database initialization."""
        if self._db is None:
            from database import get_database_manager

            self._db = get_database_manager()
        return self._db

    @property
    def provider_factory(self):
        """Lazy provider factory initialization."""
        if self._provider_factory is None:
            from data_providers import DataProviderFactory

            self._provider_factory = DataProviderFactory
        return self._provider_factory

    # ==================== Portfolio CRUD ====================

    def create_portfolio(
        self,
        name: str = "My Portfolio",
        description: str = "",
        user_id: Optional[str] = None,
        track_cash: bool = False,
        cash_balance: float = 0.0,
    ) -> str:
        """
        Create a new portfolio.

        Args:
            name: Portfolio name
            description: Portfolio description
            user_id: Owner user ID (optional)
            track_cash: Whether to track cash in this portfolio
            cash_balance: Initial cash balance (default 0)

        Returns:
            portfolio_id: Generated portfolio ID
        """
        portfolio_id = str(uuid.uuid4())
        self.db.create_portfolio(
            portfolio_id,
            name,
            description,
            user_id=user_id,
            track_cash=track_cash,
            cash_balance=cash_balance,
        )
        return portfolio_id

    def update_cash_balance(self, portfolio_id: str, cash_balance: float) -> None:
        """
        Update the cash balance for a portfolio (when track_cash is enabled).

        Args:
            portfolio_id: Portfolio ID
            cash_balance: New cash balance (must be >= 0)

        Raises:
            ValueError: If cash_balance is negative
        """
        if cash_balance < 0:
            raise ValueError("Cash balance cannot be negative")
        self.db.update_cash_balance(portfolio_id, cash_balance)

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict]:
        """
        Get portfolio by ID.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Portfolio dict or None
        """
        return self.db.get_portfolio(portfolio_id)

    def list_portfolios(self, user_id: Optional[str] = None) -> List[Dict]:
        """
        List portfolios, optionally filtered by user.

        Returns:
            List of portfolio dicts
        """
        return self.db.list_portfolios(user_id=user_id)

    def get_default_portfolio(self, user_id: Optional[str] = None) -> Dict:
        """
        Get or create the default portfolio for a user.

        Args:
            user_id: User ID (optional — falls back to legacy behavior)

        Returns:
            Default portfolio dict
        """
        if user_id is not None:
            portfolios = self.db.list_portfolios(user_id=user_id)
            if portfolios:
                return portfolios[0]
            # First login — create a personal portfolio
            portfolio_id = self.create_portfolio(user_id=user_id)
            return self.get_portfolio(portfolio_id)
        else:
            # Legacy fallback (unauthenticated callers)
            portfolios = self.db.list_portfolios()
            if portfolios:
                return portfolios[0]
            portfolio_id = self.create_portfolio()
            return self.get_portfolio(portfolio_id)

    # ==================== Holdings ====================

    CACHE_TTL_MINUTES = 15

    def get_holdings(self, portfolio_id: str, with_prices: bool = True) -> List[Dict]:
        """
        Get all holdings for a portfolio.

        Args:
            portfolio_id: Portfolio ID
            with_prices: If True (default), fetch live prices and compute
                         market value / P&L. If False, return DB data only
                         (instant, no external API calls).

        Returns:
            List of holding dicts. When with_prices=True, each dict also has:
            - current_price, market_value, unrealized_gain, unrealized_gain_pct
        """
        holdings = self.db.get_holdings(portfolio_id)

        # Filter out holdings with zero quantity (closed positions)
        holdings = [
            h for h in holdings if h.get("total_quantity", Decimal("0")) > Decimal("0")
        ]

        if not with_prices:
            for h in holdings:
                h["price_available"] = False
                h["current_price"] = None
                h["market_value"] = None
                h["unrealized_gain"] = None
                h["unrealized_gain_pct"] = None
            return holdings

        # Group by asset type
        stocks = [h for h in holdings if h["asset_type"] == "stock"]
        cryptos = [h for h in holdings if h["asset_type"] == "crypto"]
        stock_symbols = [h["symbol"] for h in stocks]
        crypto_symbols = [h["symbol"] for h in cryptos]
        all_symbols = stock_symbols + crypto_symbols

        # --- Cache lookup (fresh or stale) ---
        cached = self.db.get_cached_prices(all_symbols) if all_symbols else {}

        def _is_fresh(row):
            last = row.get("last_updated")
            if not last:
                return False
            return datetime.utcnow() - last < timedelta(minutes=self.CACHE_TTL_MINUTES)

        # Use any cached price immediately — blank only if symbol has no cache record at all
        price_map: Dict[str, Decimal] = {
            sym: Decimal(str(row["price"])) for sym, row in cached.items()
        }

        from price_cache_service import get_price_cache_service

        pcs = get_price_cache_service()

        # Fetch prices for symbols completely absent from cache
        missing_pairs = [(s, "stock") for s in stock_symbols if s not in cached] + [
            (s, "crypto") for s in crypto_symbols if s not in cached
        ]
        if missing_pairs:
            fetched = pcs.refresh(missing_pairs, force=True)
            for sym, data in fetched.items():
                price_map[sym] = data["price"]

        # Background-refresh stale cached prices (fire and forget — next call will be fresh)
        stale_pairs = [
            (s, "stock")
            for s in stock_symbols
            if s in cached and not _is_fresh(cached[s])
        ] + [
            (s, "crypto")
            for s in crypto_symbols
            if s in cached and not _is_fresh(cached[s])
        ]
        if stale_pairs:
            import threading

            threading.Thread(
                target=pcs.refresh,
                args=(stale_pairs,),
                kwargs={"force": True},
                daemon=True,
            ).start()

        # Apply prices to holdings
        for h in stocks:
            price = price_map.get(h["symbol"])
            h["current_price"] = price if price is not None else Decimal("0")
            h["price_available"] = price is not None

        for h in cryptos:
            price = price_map.get(h["symbol"])
            h["current_price"] = price if price is not None else Decimal("0")
            h["price_available"] = price is not None

        # Calculate market value and gains for all holdings
        for h in holdings:
            current_price = h.get("current_price", Decimal("0"))
            price_available = h.get("price_available", False)
            total_quantity = h.get("total_quantity", Decimal("0"))
            total_cost_basis = h.get("total_cost_basis", Decimal("0"))

            if not price_available:
                h["market_value"] = None
                h["unrealized_gain"] = None
                h["unrealized_gain_pct"] = None
            else:
                h["market_value"] = total_quantity * current_price
                h["unrealized_gain"] = h["market_value"] - total_cost_basis

                if total_cost_basis > 0:
                    h["unrealized_gain_pct"] = (
                        h["unrealized_gain"] / total_cost_basis
                    ) * 100
                else:
                    h["unrealized_gain_pct"] = Decimal("0")

        return holdings

    def get_holding(self, portfolio_id: str, symbol: str) -> Optional[Dict]:
        """
        Get a specific holding.

        Args:
            portfolio_id: Portfolio ID
            symbol: Asset symbol

        Returns:
            Holding dict or None
        """
        return self.db.get_holding(portfolio_id, symbol)

    def get_holding_by_id(self, holding_id: str) -> Optional[Dict]:
        """
        Get a holding by its ID.

        Args:
            holding_id: Holding ID

        Returns:
            Holding dict or None
        """
        return self.db.get_holding_by_id(holding_id)

    def get_holdings_for_ticker(self, user_id: str, symbol: str) -> List[Dict]:
        """
        Get all holdings of a ticker across a user's portfolios in one query.

        Returns dicts with portfolio_name included.
        """
        return self.db.get_holdings_for_ticker(user_id, symbol)

    # ==================== Transactions ====================

    def add_transaction(
        self,
        portfolio_id: str,
        symbol: str,
        transaction_type: str,
        quantity: Decimal,
        price_per_unit: Decimal,
        transaction_date: datetime,
        fees: Decimal = Decimal("0"),
        notes: str = "",
        asset_type: Optional[str] = None,
    ) -> str:
        """
        Add a transaction and recalculate holding.

        Args:
            portfolio_id: Portfolio ID
            symbol: Asset symbol
            transaction_type: 'buy' or 'sell'
            quantity: Transaction quantity
            price_per_unit: Price per unit
            transaction_date: Date of transaction
            fees: Transaction fees (optional)
            notes: Transaction notes (optional)
            asset_type: 'stock' or 'crypto' (auto-detected if not provided)

        Returns:
            transaction_id: Generated transaction ID
        """
        # Normalize symbol
        symbol = symbol.upper().replace("CRYPTO:", "").strip()

        # Auto-detect asset type if not provided
        if asset_type is None:
            asset_type = self.provider_factory.detect_asset_type(symbol)

        # Validate transaction type
        if transaction_type not in ("buy", "sell"):
            raise ValueError(f"Invalid transaction type: {transaction_type}")

        # Get or create holding
        holding = self.db.get_holding(portfolio_id, symbol)
        if holding is None:
            holding_id = str(uuid.uuid4())
            self.db.create_holding(holding_id, portfolio_id, symbol, asset_type)
        else:
            holding_id = holding["holding_id"]

        # Add transaction
        transaction_id = str(uuid.uuid4())
        self.db.add_transaction(
            transaction_id=transaction_id,
            holding_id=holding_id,
            transaction_type=transaction_type,
            quantity=quantity,
            price_per_unit=price_per_unit,
            fees=fees,
            transaction_date=transaction_date,
            notes=notes,
            import_source="manual",
        )

        # Recalculate holding totals
        self._recalculate_holding(holding_id)

        return transaction_id

    def get_transactions(self, holding_id: str) -> List[Dict]:
        """
        Get all transactions for a holding.

        Args:
            holding_id: Holding ID

        Returns:
            List of transaction dicts
        """
        return self.db.get_transactions(holding_id)

    def get_transaction(self, transaction_id: str) -> Optional[Dict]:
        """
        Get a single transaction.

        Args:
            transaction_id: Transaction ID

        Returns:
            Transaction dict or None
        """
        return self.db.get_transaction(transaction_id)

    def delete_transaction(self, transaction_id: str) -> bool:
        """
        Delete a transaction and recalculate holding.

        Args:
            transaction_id: Transaction ID

        Returns:
            True if deleted, False if not found
        """
        txn = self.db.get_transaction(transaction_id)
        if not txn:
            return False

        holding_id = txn["holding_id"]
        self.db.delete_transaction(transaction_id)
        self._recalculate_holding(holding_id)
        return True

    def _recalculate_holding(self, holding_id: str):
        """
        Recalculate holding totals from transactions.

        Args:
            holding_id: Holding ID
        """
        transactions = self.db.get_transactions(holding_id)

        if not transactions:
            # No transactions left — delete the holding row entirely so it
            # doesn't appear as a ghost row in exports or future queries.
            self.db.delete_holding(holding_id)
            return

        # Calculate using simple average method
        result = calculate_simple_average(transactions)

        self.db.update_holding(
            holding_id=holding_id,
            total_quantity=result.total_quantity,
            average_cost=result.average_cost,
            total_cost_basis=result.total_cost_basis,
        )

    # ==================== CSV Import ====================

    def import_csv(
        self, portfolio_id: str, csv_content: str, filename: str
    ) -> ImportResult:
        """
        Import transactions from CSV.

        Args:
            portfolio_id: Portfolio ID
            csv_content: Raw CSV string content
            filename: Original filename for logging

        Returns:
            ImportResult with success/error counts
        """
        # Parse CSV
        result = self.csv_importer.parse_csv(csv_content)

        # Add each transaction
        successful = 0
        cash_delta = Decimal("0")
        for txn in result.transactions:
            try:
                if txn["transaction_type"] == "cash_in":
                    cash_delta += Decimal(str(txn["amount"]))
                    successful += 1
                elif txn["transaction_type"] == "cash_out":
                    cash_delta -= Decimal(str(txn["amount"]))
                    successful += 1
                else:
                    self.add_transaction(
                        portfolio_id=portfolio_id,
                        symbol=txn["symbol"],
                        transaction_type=txn["transaction_type"],
                        quantity=txn["quantity"],
                        price_per_unit=txn["price_per_unit"],
                        transaction_date=txn["transaction_date"],
                        fees=txn["fees"],
                        notes=txn.get("notes", ""),
                    )
                    successful += 1
            except Exception as e:
                result.errors.append({"row": "import", "error": str(e), "data": txn})

        # Apply cash delta if any cash rows were present
        if cash_delta != Decimal("0"):
            portfolio = self.db.get_portfolio(portfolio_id)
            current_cash = Decimal(str(portfolio.get("cash_balance", 0) or 0))
            new_balance = max(Decimal("0"), current_cash + cash_delta)
            self.db.update_cash_balance(portfolio_id, float(new_balance))

        # Update counts
        result.success_count = successful
        result.error_count = len(result.errors)

        # Log import
        import_id = str(uuid.uuid4())
        self.db.log_csv_import(
            import_id=import_id,
            portfolio_id=portfolio_id,
            filename=filename,
            row_count=len(result.transactions) + len(result.errors),
            success_count=result.success_count,
            error_count=result.error_count,
            errors_json=result.errors,
        )

        return result

    def preview_csv(self, csv_content: str) -> Dict:
        """
        Preview CSV content without importing.

        Args:
            csv_content: Raw CSV string

        Returns:
            Preview dict with format, headers, sample rows
        """
        return self.csv_importer.preview_csv(csv_content)

    # ==================== Portfolio Summary ====================

    def get_portfolio_summary(
        self, portfolio_id: str, with_prices: bool = True
    ) -> Dict:
        """
        Get portfolio summary with totals and allocation.

        Args:
            portfolio_id: Portfolio ID
            with_prices: Whether to fetch live prices (default True).
                         Pass False for an instant render using DB data only;
                         price-dependent fields will be None.

        Returns:
            Summary dict with:
            - prices_loaded: bool indicating whether live prices were fetched
            - total_cost_basis
            - total_market_value (None when with_prices=False)
            - total_unrealized_gain (None when with_prices=False)
            - total_unrealized_gain_pct (None when with_prices=False)
            - holdings_count
            - stock_allocation_pct, crypto_allocation_pct (None when with_prices=False)
            - track_cash, cash_balance, cash_value, cash_allocation_pct (when track_cash)
            - holdings (list)
        """
        portfolio = self.db.get_portfolio(portfolio_id)
        track_cash = portfolio.get("track_cash", False) if portfolio else False
        cash_balance = (
            Decimal(str(portfolio.get("cash_balance", 0) or 0))
            if portfolio
            else Decimal("0")
        )

        holdings = self.get_holdings(portfolio_id, with_prices=with_prices)

        total_cost_basis = sum(
            h.get("total_cost_basis", Decimal("0")) for h in holdings
        )
        if track_cash:
            total_cost_basis += cash_balance

        if with_prices:
            total_market_value = sum(
                h.get("market_value") or Decimal("0") for h in holdings
            )
            if track_cash:
                total_market_value += cash_balance
            total_unrealized_gain = total_market_value - total_cost_basis
            total_unrealized_gain_pct = (
                (total_unrealized_gain / total_cost_basis) * 100
                if total_cost_basis > 0
                else Decimal("0")
            )
            stock_value = sum(
                h.get("market_value") or Decimal("0")
                for h in holdings
                if h["asset_type"] == "stock"
            )
            crypto_value = sum(
                h.get("market_value") or Decimal("0")
                for h in holdings
                if h["asset_type"] == "crypto"
            )
            cash_value = cash_balance if track_cash else Decimal("0")
            if total_market_value > 0:
                stock_allocation_pct = (stock_value / total_market_value) * 100
                crypto_allocation_pct = (crypto_value / total_market_value) * 100
                cash_allocation_pct = (
                    (cash_value / total_market_value) * 100
                    if track_cash
                    else Decimal("0")
                )
            else:
                stock_allocation_pct = crypto_allocation_pct = cash_allocation_pct = (
                    Decimal("0")
                )
        else:
            total_market_value = None
            total_unrealized_gain = None
            total_unrealized_gain_pct = None
            stock_allocation_pct = None
            crypto_allocation_pct = None
            cash_value = cash_balance if track_cash else Decimal("0")
            cash_allocation_pct = None

        result = {
            "portfolio_id": portfolio_id,
            "prices_loaded": with_prices,
            "total_cost_basis": total_cost_basis,
            "total_market_value": total_market_value,
            "total_unrealized_gain": total_unrealized_gain,
            "total_unrealized_gain_pct": total_unrealized_gain_pct,
            "holdings_count": len(holdings),
            "stock_allocation_pct": stock_allocation_pct,
            "crypto_allocation_pct": crypto_allocation_pct,
            "holdings": holdings,
        }
        if track_cash:
            result["track_cash"] = True
            result["cash_balance"] = cash_balance
            result["cash_value"] = cash_value
            result["cash_allocation_pct"] = cash_allocation_pct
        return result

    def get_portfolios_with_summaries(self, user_id: Optional[str] = None) -> Dict:
        """
        List portfolios with light summary per portfolio and overall aggregate.
        For list view: no full holdings, just value/P&L/count.

        Args:
            user_id: User ID (optional)

        Returns:
            Dict with:
            - portfolios: list of portfolio dicts, each with 'summary' (light: total_market_value,
              total_cost_basis, total_unrealized_gain, total_unrealized_gain_pct, holdings_count)
            - overall: total_market_value, total_cost_basis, total_unrealized_gain,
              total_unrealized_gain_pct, total_holdings_count (or None if no portfolios)
        """
        portfolios = self.list_portfolios(user_id=user_id)
        if not portfolios:
            return {"portfolios": [], "overall": None}

        total_cost_basis = Decimal("0")
        total_holdings_count = 0

        for p in portfolios:
            pid = p.get("portfolio_id")
            try:
                summary = self.get_portfolio_summary(pid, with_prices=False)
                p["summary"] = {
                    "total_cost_basis": summary["total_cost_basis"],
                    "holdings_count": summary["holdings_count"],
                }
                total_cost_basis += summary["total_cost_basis"]
                total_holdings_count += summary["holdings_count"]
            except Exception:
                holdings = self.db.get_holdings(pid)
                count = len(holdings)
                p["summary"] = {
                    "total_cost_basis": Decimal("0"),
                    "holdings_count": count,
                }
                total_holdings_count += count

        overall = {
            "total_cost_basis": total_cost_basis,
            "total_holdings_count": total_holdings_count,
        }
        return {"portfolios": portfolios, "overall": overall}

    # ==================== Allocation Breakdowns ====================

    def get_allocation_breakdowns_from_summary(self, summary: Dict) -> Dict:
        """
        Compute lightweight breakdowns for the portfolio detail page.

        Returns:
            Dict:
              - prices_loaded: bool
              - market: [{label, value, pct}]
              - sector: [{label, value, pct}] (stocks only; pct is of total portfolio MV)
        """

        def _to_decimal(v) -> Decimal:
            if v is None:
                return Decimal("0")
            if isinstance(v, Decimal):
                return v
            return Decimal(str(v))

        prices_loaded = bool(summary.get("prices_loaded"))
        holdings = summary.get("holdings") or []

        if not prices_loaded:
            return {"prices_loaded": False, "sector": [], "market": []}

        total_market_value = _to_decimal(summary.get("total_market_value"))
        if total_market_value <= 0:
            return {"prices_loaded": True, "sector": [], "market": []}

        # ---- Market (asset-class) breakdown ----
        market_values: Dict[str, Decimal] = {
            "US Stocks": Decimal("0"),
            "Crypto": Decimal("0"),
        }
        for h in holdings:
            if not h.get("price_available"):
                continue
            mv = h.get("market_value")
            if mv is None:
                continue
            asset_type = (h.get("asset_type") or "").lower()
            if asset_type == "crypto":
                market_values["Crypto"] += _to_decimal(mv)
            else:
                # Default to stock bucket
                market_values["US Stocks"] += _to_decimal(mv)

        if summary.get("track_cash"):
            market_values["Cash"] = _to_decimal(summary.get("cash_value"))

        market = []
        for label, value in market_values.items():
            if value <= 0:
                continue
            pct = (value / total_market_value) * 100
            market.append({"label": label, "value": float(value), "pct": float(pct)})
        market.sort(key=lambda r: r["pct"], reverse=True)

        # ---- Sector breakdown (stocks only) ----
        sector_values: Dict[str, Decimal] = {}
        try:
            stock_provider = self.provider_factory.get_provider("stock")
        except Exception:
            stock_provider = None

        sector_cache: Dict[str, str] = {}

        for h in holdings:
            if (h.get("asset_type") or "").lower() != "stock":
                continue
            if not h.get("price_available"):
                continue
            mv = h.get("market_value")
            if mv is None:
                continue

            symbol = (h.get("symbol") or "").upper()
            sector = sector_cache.get(symbol)
            if sector is None:
                sector = ""
                if stock_provider is not None and symbol:
                    try:
                        info = stock_provider.get_asset_info(symbol)
                        sector = (info or {}).get("sector") or ""
                    except Exception:
                        sector = ""
                sector_cache[symbol] = sector

            label = (sector or "Unknown").strip() or "Unknown"
            sector_values[label] = sector_values.get(label, Decimal("0")) + _to_decimal(
                mv
            )

        sector = []
        for label, value in sector_values.items():
            if value <= 0:
                continue
            pct = (value / total_market_value) * 100
            sector.append({"label": label, "value": float(value), "pct": float(pct)})
        sector.sort(key=lambda r: r["pct"], reverse=True)

        return {"prices_loaded": True, "sector": sector, "market": market}


# Global service instance
_portfolio_service: Optional[PortfolioService] = None


def get_portfolio_service() -> PortfolioService:
    """Get or create global portfolio service instance."""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = PortfolioService()
    return _portfolio_service
