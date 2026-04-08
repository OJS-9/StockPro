"""
Shared pytest configuration and markers.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="Run integration tests that hit real APIs (SEC EDGAR, Gemini, yfinance).",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--integration"):
        return
    skip_integration = pytest.mark.skip(reason="Need --integration flag to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
