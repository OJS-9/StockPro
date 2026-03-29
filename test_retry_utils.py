"""Tests for shared retry helpers."""

import pytest

from retry_utils import (
    exponential_backoff_seconds,
    is_rate_limit_error,
    run_with_exponential_backoff,
)


def test_exponential_backoff_seconds():
    assert exponential_backoff_seconds(0, 2.0) == 2.0
    assert exponential_backoff_seconds(1, 2.0) == 4.0
    assert exponential_backoff_seconds(2, 1.0) == 4.0


def test_is_rate_limit_error_detects_429():
    exc = type("E", (), {"status_code": 429})()
    assert is_rate_limit_error(exc) is True


def test_is_rate_limit_error_detects_message():
    assert is_rate_limit_error(RuntimeError("Resource exhausted")) is True
    assert is_rate_limit_error(RuntimeError("something else")) is False


def test_run_with_exponential_backoff_succeeds_first_try():
    calls = {"n": 0}

    def ok():
        calls["n"] += 1
        return 42

    assert (
        run_with_exponential_backoff(
            ok,
            max_retries=3,
            base_delay_seconds=0.01,
            is_retriable=lambda e: True,
        )
        == 42
    )
    assert calls["n"] == 1


def test_run_with_exponential_backoff_raises_after_retries():
    class Flaky(Exception):
        pass

    calls = {"n": 0}

    def always_fail():
        calls["n"] += 1
        raise Flaky("fail")

    with pytest.raises(Flaky):
        run_with_exponential_backoff(
            always_fail,
            max_retries=2,
            base_delay_seconds=0.01,
            is_retriable=lambda e: isinstance(e, Flaky),
        )
    assert calls["n"] == 2
