"""
Shared retry helpers for LLM calls, HTTP clients, and external tools.

Centralizes exponential backoff and rate-limit detection so agent nodes and
data clients stay consistent (Phase 1.7 roadmap).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def is_rate_limit_error(exc: BaseException) -> bool:
    """True for HTTP 429 / Gemini resource exhausted / common quota strings."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429:
        return True
    message = str(exc).lower()
    return (
        "resource exhausted" in message or "rate limit" in message or "429" in message
    )


def exponential_backoff_seconds(attempt: int, base_delay: float) -> float:
    """Attempt is zero-based; delay grows as base * 2**attempt."""
    return base_delay * (2**attempt)


def run_with_exponential_backoff(
    operation: Callable[[], T],
    *,
    max_retries: int,
    base_delay_seconds: float,
    is_retriable: Callable[[BaseException], bool],
    log_label: str = "operation",
) -> T:
    """
    Run `operation`, retrying on retriable errors with exponential backoff.

    Raises the last exception if all attempts fail or the error is not retriable.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(max_retries):
        try:
            return operation()
        except BaseException as exc:
            last_exc = exc
            if not is_retriable(exc) or attempt == max_retries - 1:
                raise
            delay = exponential_backoff_seconds(attempt, base_delay_seconds)
            logger.warning(
                "[%s] Retriable error (%s), retrying in %.1fs",
                log_label,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
