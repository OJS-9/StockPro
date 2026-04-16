"""HTTP client wrapper with auth headers and error handling."""

import sys
import json
import httpx
from stockpro_cli.config import get_api_url, get_token


class StockProClient:
    def __init__(self, api_url: str, token: str):
        self._base = api_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=120.0,
        )

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _handle(self, resp: httpx.Response) -> dict:
        if resp.status_code == 401:
            _error(f"Unauthorized. Run: stockpro auth login (server: {resp.text[:200]})")
        if resp.status_code == 403:
            _error(f"Forbidden ({resp.text[:200]})")
        if resp.status_code == 404:
            _error("Not found.")
        if resp.status_code == 429:
            _error("Rate limited. Try again later.")
        if resp.status_code >= 500:
            _error(f"Server error ({resp.status_code}): {resp.text[:200]}")
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._handle(self._client.get(self._url(path), params=params))

    def post(self, path: str, data: dict | None = None) -> dict:
        return self._handle(self._client.post(self._url(path), json=data))

    def put(self, path: str, data: dict | None = None) -> dict:
        return self._handle(self._client.put(self._url(path), json=data))

    def patch(self, path: str, data: dict | None = None) -> dict:
        return self._handle(self._client.patch(self._url(path), json=data))

    def delete(self, path: str) -> dict:
        return self._handle(self._client.delete(self._url(path)))


def _error(msg: str):
    json.dump({"error": msg}, sys.stderr)
    sys.stderr.write("\n")
    sys.exit(1)


def get_client(api_url: str | None = None) -> StockProClient:
    url = api_url or get_api_url()
    token = get_token()
    if not token:
        _error("Not authenticated. Run: stockpro auth login")
    return StockProClient(url, token)
