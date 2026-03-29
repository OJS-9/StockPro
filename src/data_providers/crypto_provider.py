"""
Crypto data provider using CoinGecko API.
"""

import requests
from decimal import Decimal
from typing import Dict, Optional

from .base_provider import BaseDataProvider


class CryptoDataProvider(BaseDataProvider):
    """Crypto data provider using CoinGecko API (free tier)."""

    BASE_URL = "https://api.coingecko.com/api/v3"

    # Common symbol to CoinGecko ID mapping
    SYMBOL_MAP = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "ADA": "cardano",
        "DOT": "polkadot",
        "MATIC": "matic-network",
        "AVAX": "avalanche-2",
        "LINK": "chainlink",
        "UNI": "uniswap",
        "ATOM": "cosmos",
        "XRP": "ripple",
        "DOGE": "dogecoin",
        "SHIB": "shiba-inu",
        "LTC": "litecoin",
        "BCH": "bitcoin-cash",
        "XLM": "stellar",
        "ALGO": "algorand",
        "VET": "vechain",
        "FIL": "filecoin",
        "AAVE": "aave",
        "MKR": "maker",
        "NEAR": "near",
        "APT": "aptos",
        "ARB": "arbitrum",
        "OP": "optimism",
        "SUI": "sui",
        "SEI": "sei-network",
        "INJ": "injective-protocol",
        "TIA": "celestia",
        "PEPE": "pepe",
        "WIF": "dogwifcoin",
        "BONK": "bonk",
    }

    def __init__(self):
        """Initialize crypto data provider."""
        super().__init__()
        self._coin_list_cache = (
            None  # in-process cache for the static CoinGecko coin list only
        )
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
            }
        )

    def _get_coin_id(self, symbol: str) -> Optional[str]:
        """
        Convert symbol to CoinGecko coin ID.

        Args:
            symbol: Crypto symbol (e.g., 'BTC', 'ETH')

        Returns:
            CoinGecko coin ID, or None if not found
        """
        symbol_upper = symbol.upper().replace("CRYPTO:", "")

        # Check known mappings first
        if symbol_upper in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[symbol_upper]

        # Fallback: search coin list (cached)
        if self._coin_list_cache is None:
            try:
                resp = self._session.get(f"{self.BASE_URL}/coins/list", timeout=10)
                if resp.ok:
                    self._coin_list_cache = resp.json()
            except Exception:
                self._coin_list_cache = []

        if self._coin_list_cache:
            for coin in self._coin_list_cache:
                if coin.get("symbol", "").upper() == symbol_upper:
                    return coin.get("id")

        return None

    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get current crypto price from CoinGecko.

        Args:
            symbol: Crypto symbol (e.g., 'BTC', 'ETH')

        Returns:
            Current price in USD as Decimal, or None if unavailable
        """
        coin_id = self._get_coin_id(symbol)
        if not coin_id:
            return None

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": coin_id, "vs_currencies": "usd"},
                timeout=10,
            )

            if resp.ok:
                data = resp.json()
                if coin_id in data and "usd" in data[coin_id]:
                    return Decimal(str(data[coin_id]["usd"]))

        except Exception as e:
            print(f"Error fetching crypto price for {symbol}: {e}")

        return None

    def get_prices_batch(self, symbols: list) -> Dict[str, Decimal]:
        """
        Get prices for multiple cryptos in one API call.

        Args:
            symbols: List of crypto symbols

        Returns:
            Dict mapping symbol to price
        """
        if not symbols:
            return {}

        # Map symbols to coin IDs
        coin_ids = []
        id_to_symbol = {}

        for symbol in symbols:
            coin_id = self._get_coin_id(symbol)
            if coin_id:
                coin_ids.append(coin_id)
                id_to_symbol[coin_id] = symbol.upper().replace("CRYPTO:", "")

        if not coin_ids:
            return {}

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/simple/price",
                params={"ids": ",".join(coin_ids), "vs_currencies": "usd"},
                timeout=10,
            )

            if resp.ok:
                data = resp.json()
                prices = {}

                for coin_id, price_data in data.items():
                    symbol = id_to_symbol.get(coin_id)
                    if symbol and "usd" in price_data:
                        prices[symbol] = Decimal(str(price_data["usd"]))

                return prices

        except Exception as e:
            print(f"Error fetching batch crypto prices: {e}")

        return {}

    def get_prices_with_change(self, symbols: list) -> dict:
        """Get prices and 24hr change% for multiple cryptos in one call."""
        if not symbols:
            return {}

        coin_ids = []
        id_to_symbol = {}
        for symbol in symbols:
            coin_id = self._get_coin_id(symbol)
            if coin_id:
                coin_ids.append(coin_id)
                id_to_symbol[coin_id] = symbol.upper().replace("CRYPTO:", "")

        if not coin_ids:
            return {}

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/simple/price",
                params={
                    "ids": ",".join(coin_ids),
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
                timeout=10,
            )
            if resp.ok:
                data = resp.json()
                result = {}
                for coin_id, price_data in data.items():
                    symbol = id_to_symbol.get(coin_id)
                    if symbol and "usd" in price_data:
                        price = Decimal(str(price_data["usd"]))
                        change = price_data.get("usd_24h_change")
                        change_decimal = (
                            Decimal(str(round(change, 4)))
                            if change is not None
                            else None
                        )
                        result[symbol] = {
                            "price": price,
                            "change_percent": change_decimal,
                        }
                return result
        except Exception as e:
            print(f"Error fetching crypto prices with change: {e}")

        return {}

    def validate_symbol(self, symbol: str) -> bool:
        """
        Check if crypto symbol is valid.

        Args:
            symbol: Crypto symbol

        Returns:
            True if valid, False otherwise
        """
        return self._get_coin_id(symbol) is not None

    def get_asset_info(self, symbol: str) -> Optional[Dict]:
        """
        Get detailed coin information.

        Args:
            symbol: Crypto symbol

        Returns:
            Dict with coin info, or None if unavailable
        """
        coin_id = self._get_coin_id(symbol)
        if not coin_id:
            return None

        try:
            resp = self._session.get(
                f"{self.BASE_URL}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "community_data": "false",
                    "developer_data": "false",
                },
                timeout=15,
            )

            if resp.ok:
                data = resp.json()
                market_data = data.get("market_data", {})

                return {
                    "symbol": data.get("symbol", "").upper(),
                    "name": data.get("name", ""),
                    "description": data.get("description", {}).get("en", "")[
                        :500
                    ],  # Truncate
                    "market_cap": market_data.get("market_cap", {}).get("usd"),
                    "market_cap_rank": data.get("market_cap_rank"),
                    "volume_24h": market_data.get("total_volume", {}).get("usd"),
                    "price_change_24h": market_data.get("price_change_percentage_24h"),
                    "price_change_7d": market_data.get("price_change_percentage_7d"),
                    "price_change_30d": market_data.get("price_change_percentage_30d"),
                    "circulating_supply": market_data.get("circulating_supply"),
                    "total_supply": market_data.get("total_supply"),
                    "max_supply": market_data.get("max_supply"),
                    "ath": market_data.get("ath", {}).get("usd"),
                    "ath_date": market_data.get("ath_date", {}).get("usd"),
                    "atl": market_data.get("atl", {}).get("usd"),
                    "atl_date": market_data.get("atl_date", {}).get("usd"),
                }

        except Exception as e:
            print(f"Error fetching asset info for {symbol}: {e}")

        return None
