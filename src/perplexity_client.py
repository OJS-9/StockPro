"""
Perplexity Sonar API client for real-time web research.
Uses httpx directly (no OpenAI wrapper).
"""

import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

PERPLEXITY_TIMEOUT_SECONDS = float(os.getenv("PERPLEXITY_TIMEOUT_SECONDS", "10.0"))


class PerplexityClient:
    """
    Synchronous client for Perplexity's Sonar API.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "sonar"):
        self.api_key = api_key or os.getenv("PERPLEXITY_API_KEY")
        self.model = model or os.getenv("PERPLEXITY_MODEL", "sonar")
        self.timeout = PERPLEXITY_TIMEOUT_SECONDS

        if not self.api_key:
            raise ValueError(
                "PERPLEXITY_API_KEY is required. "
                "Set PERPLEXITY_API_KEY environment variable or pass api_key parameter."
            )

    def research(
        self,
        query: str,
        system_message: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2000,
    ) -> str:
        """
        Perform a research query using Perplexity Sonar API.

        Returns:
            Research response content as string
        """
        messages = [
            {
                "role": "system",
                "content": system_message or "You are a helpful research assistant that provides accurate, cited information.",
            },
            {"role": "user", "content": query},
        ]

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices") or []
                if not choices:
                    return ""
                msg = choices[0].get("message") or {}
                return msg.get("content") or ""
        except httpx.TimeoutException as e:
            return (
                f"[Perplexity timeout] Research request exceeded "
                f"{self.timeout:.0f}s limit: {e}"
            )
        except Exception as e:
            return f"[Perplexity error] Research request failed: {e}"


def create_perplexity_client(api_key: Optional[str] = None, model: Optional[str] = None) -> PerplexityClient:
    return PerplexityClient(api_key=api_key, model=model or "sonar")
