"""HTTP client wrapper with auth headers and structured error handling."""

import sys
import json
import click
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
            data = resp.json()
        except Exception:
            return {"raw": resp.text}
        if isinstance(data, list):
            return {"items": data, "page": 1, "has_more": False}
        return data

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            resp = self._client.request(method, self._url(path), **kwargs)
        except httpx.ConnectError as exc:
            _error(f"Cannot reach server at {self._base}: {exc}")
        except httpx.TimeoutException as exc:
            _error(f"Request timed out: {exc}")
        except httpx.RequestError as exc:
            _error(f"Network error: {exc}")
        return self._handle(resp)

    def get(self, path: str, params: dict | None = None) -> dict:
        return self._request("GET", path, params=params)

    def post(self, path: str, data: dict | None = None) -> dict:
        return self._request("POST", path, json=data)

    def put(self, path: str, data: dict | None = None) -> dict:
        return self._request("PUT", path, json=data)

    def patch(self, path: str, data: dict | None = None) -> dict:
        return self._request("PATCH", path, json=data)

    def delete(self, path: str) -> dict:
        return self._request("DELETE", path)


def _error(msg: str):
    click.echo(json.dumps({"error": msg}), err=True)
    sys.exit(1)


def get_client(api_url: str | None = None) -> StockProClient:
    url = api_url or get_api_url()
    token = get_token()
    if not token:
        _error("Not authenticated. Run: stockpro auth login")
    return StockProClient(url, token)
