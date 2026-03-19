"""
Nimble API client for web search and content extraction.
Uses Nimble's SDK REST API with Bearer token authentication.
"""

import os
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv

load_dotenv()

NIMBLE_API_BASE = "https://sdk.nimbleway.com/v1"
NIMBLE_TIMEOUT_SECONDS = float(os.getenv("NIMBLE_TIMEOUT_SECONDS", "60.0"))
NIMBLE_FAST_TIMEOUT_SECONDS = float(os.getenv("NIMBLE_FAST_TIMEOUT_SECONDS", "15.0"))

_FOCUS_PREFIXES = {
    "news": "As a financial news research assistant focusing on recent events and sources: ",
    "analysis": "As a financial analysis assistant providing expert opinions with sources: ",
    "financial": "As a financial market research assistant covering market trends with sources: ",
    "general": "",
}


class NimbleClient:
    """Synchronous client for Nimble's web search and extraction API."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NIMBLE_API_KEY")
        if not self.api_key:
            raise ValueError(
                "NIMBLE_API_KEY is required. "
                "Set NIMBLE_API_KEY environment variable or pass api_key parameter."
            )
        self.timeout = NIMBLE_TIMEOUT_SECONDS

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def extract(self, url: str, render: bool = False) -> Dict[str, Any]:
        """
        Extract and parse content from a specific URL.

        Args:
            url: Target URL to extract content from
            render: Enable JS rendering via headless browser

        Returns:
            Extraction result dict (data.markdown, data.html, etc.)
        """
        payload: Dict[str, Any] = {
            "url": url,
            "render": render,
            "formats": ["markdown"],
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{NIMBLE_API_BASE}/extract",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException as e:
            return {"error": f"[Nimble timeout] Extract exceeded {self.timeout:.0f}s: {e}"}
        except Exception as e:
            return {"error": f"[Nimble error] Extract failed: {e}"}

    def search(
        self,
        query: str,
        num_results: int = 5,
        topic: str = "general",
        time_range: Optional[str] = None,
        deep_search: bool = False,
    ) -> Dict[str, Any]:
        """
        Perform a web search.

        Args:
            query: Search query string
            num_results: Number of results to return (default 5, recommend max 3 with deep_search=True)
            topic: Search topic filter — "general", "news", "shopping", "social"
            time_range: Time filter — "hour", "day", "week", "month", "year"
            deep_search: If True, fetches full page content for each result (slower, 15-45s).
                         If False (default), returns title/snippet/URL only (fast, 1-5s).

        Returns:
            Search results dict with results[], total_results, optional answer
        """
        payload: Dict[str, Any] = {
            "query": query,
            "num_results": num_results,
            "parsing_type": "markdown",
            "topic": topic,
            "deep_search": deep_search,
        }
        if time_range:
            payload["time_range"] = time_range

        timeout = self.timeout if deep_search else NIMBLE_FAST_TIMEOUT_SECONDS
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    f"{NIMBLE_API_BASE}/search",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.TimeoutException as e:
            return {"error": f"[Nimble timeout] Search exceeded {timeout:.0f}s: {e}"}
        except Exception as e:
            return {"error": f"[Nimble error] Search failed: {e}"}

    def perplexity_research(self, query: str, focus: str = "general") -> str:
        """
        Run a query through Nimble's hosted Perplexity agent.

        Args:
            query: Research query string
            focus: Focus type — "news", "analysis", "financial", "general"

        Returns:
            Response string from Perplexity via Nimble agent
        """
        prefix = _FOCUS_PREFIXES.get(focus, "")
        prompt = f"{prefix}{query}"
        payload = {"agent": "perplexity", "params": {"prompt": prompt}}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{NIMBLE_API_BASE}/agents/run",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"]["parsing"]["parsed"]["response"]
        except httpx.TimeoutException as e:
            return f"[Nimble Perplexity timeout] Exceeded {self.timeout:.0f}s: {e}"
        except Exception as e:
            return f"[Nimble Perplexity error] Request failed: {e}"

    def run_agent(self, agent_name: str, params: dict) -> list:
        """
        Run a Nimble pre-built agent and return its parsed results as a list.

        Args:
            agent_name: Agent ID (e.g. 'bloomberg_search_...')
            params: Input parameters matching the agent's input schema

        Returns:
            List of result dicts (or other serializable items), or empty list on failure.

        Notes:
            Nimble agent responses are not consistent across agents:
            - Some return `data.parsing` as a list directly.
            - Some return `data.parsing` as a dict where one value is the list.
            - Some return `data.parsing` as a dict representing a single record
              (e.g., fields like `price`, `change`, `ticker`).

            This helper normalizes those shapes into a list.
        """
        payload = {"agent": agent_name, "params": params}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    f"{NIMBLE_API_BASE}/agents/run",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                parsing = resp.json().get("data", {}).get("parsing", [])

                # Most common: already a list of records.
                if isinstance(parsing, list):
                    return parsing

                # Dict shapes:
                if isinstance(parsing, dict):
                    # Some agents wrap actual results under `parsed`.
                    maybe_parsed = parsing.get("parsed")
                    if isinstance(maybe_parsed, list):
                        return maybe_parsed
                    if isinstance(maybe_parsed, dict):
                        return [maybe_parsed]
                    if isinstance(maybe_parsed, str):
                        return [maybe_parsed]

                    # If exactly one dict value is a list, return that list.
                    list_values = [v for v in parsing.values() if isinstance(v, list)]
                    if len(list_values) == 1:
                        return list_values[0]

                    # Otherwise treat the dict as a single record.
                    return [parsing]

                # Fallback: wrap scalar into a list so callers can iterate safely.
                return [parsing]
        except Exception:
            return []
