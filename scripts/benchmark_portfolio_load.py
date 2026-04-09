"""
Benchmark: 3 approaches for portfolio detail prefetch speed.

Approach A (Current): List endpoint -> N separate detail calls (sequential from frontend)
Approach B (Batch): List endpoint -> 1 batch call for all portfolio details (parallel server-side)
Approach C (Enriched): 1 enriched list endpoint that returns full holdings per portfolio

Runs each approach 3 times, reports avg/min/max.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from portfolio.portfolio_service import get_portfolio_service
from price_cache_service import get_price_cache_service

USER_ID = "user_3AtTsnz7x34bHQwLH7s8v1LCaMi"
RUNS = 3


def clear_price_cache():
    """Force stale cache so each run actually fetches prices."""
    pcs = get_price_cache_service()
    # Touch nothing — we want warm cache to simulate real user flow
    # (prices are already cached from previous calls)


def approach_a_current():
    """
    Current flow: /api/portfolios/prices (list summaries) + N x /api/portfolio/<id>/prices (detail).
    This is what the frontend does today.
    """
    ps = get_portfolio_service()
    from concurrent.futures import ThreadPoolExecutor

    # Step 1: List call (same as /api/portfolios/prices)
    portfolios = ps.list_portfolios(user_id=USER_ID)
    pids = [p["portfolio_id"] for p in portfolios]

    def _list_summary(pid):
        return ps.get_portfolio_summary(pid, with_prices=True)

    with ThreadPoolExecutor(max_workers=min(len(pids), 5)) as pool:
        list_futures = {pid: pool.submit(_list_summary, pid) for pid in pids}
    list_results = {pid: f.result() for pid, f in list_futures.items()}

    # Step 2: N detail calls (same as frontend prefetching each /api/portfolio/<id>/prices)
    # These are SEQUENTIAL from the frontend perspective (waterfall of fetches)
    detail_results = {}
    for pid in pids:
        detail_results[pid] = ps.get_portfolio_summary(pid, with_prices=True)

    return list_results, detail_results


def approach_b_batch():
    """
    New batch endpoint: /api/portfolios/prices (list) + 1 batch call that fetches all details in parallel.
    """
    ps = get_portfolio_service()
    from concurrent.futures import ThreadPoolExecutor

    # Step 1: List call
    portfolios = ps.list_portfolios(user_id=USER_ID)
    pids = [p["portfolio_id"] for p in portfolios]

    def _summary(pid):
        return ps.get_portfolio_summary(pid, with_prices=True)

    with ThreadPoolExecutor(max_workers=min(len(pids), 5)) as pool:
        list_futures = {pid: pool.submit(_summary, pid) for pid in pids}
    list_results = {pid: f.result() for pid, f in list_futures.items()}

    # Step 2: ONE batch call — all detail summaries in parallel
    with ThreadPoolExecutor(max_workers=min(len(pids), 5)) as pool:
        detail_futures = {pid: pool.submit(_summary, pid) for pid in pids}
    detail_results = {pid: f.result() for pid, f in detail_futures.items()}

    return list_results, detail_results


def approach_c_enriched():
    """
    Single enriched call: /api/portfolios/prices returns full holdings per portfolio.
    Frontend seeds both list and detail caches from the single response.
    No second round of calls needed.
    """
    ps = get_portfolio_service()
    from concurrent.futures import ThreadPoolExecutor

    # Step 1: ONE enriched call — returns list totals + full holdings per portfolio
    portfolios = ps.list_portfolios(user_id=USER_ID)
    pids = [p["portfolio_id"] for p in portfolios]

    def _full_summary(pid):
        summary = ps.get_portfolio_summary(pid, with_prices=True)
        # Return everything — totals AND full holdings list
        return summary

    with ThreadPoolExecutor(max_workers=min(len(pids), 5)) as pool:
        futures = {pid: pool.submit(_full_summary, pid) for pid in pids}
    results = {pid: f.result() for pid, f in futures.items()}

    # No step 2 — the frontend can extract list totals AND detail holdings from the same data
    return results, results  # same data serves both purposes


def benchmark(name, fn):
    times = []
    for i in range(RUNS):
        start = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        print(f"  Run {i + 1}: {elapsed:.3f}s")
    avg = sum(times) / len(times)
    print(f"  >> {name}: avg={avg:.3f}s  min={min(times):.3f}s  max={max(times):.3f}s\n")
    return avg


if __name__ == "__main__":
    print(f"User: {USER_ID}")
    print(f"Runs per approach: {RUNS}\n")

    # Warm up price cache first so we benchmark steady-state (not cold yfinance fetches)
    print("Warming price cache...")
    ps = get_portfolio_service()
    portfolios = ps.list_portfolios(user_id=USER_ID)
    for p in portfolios:
        ps.get_portfolio_summary(p["portfolio_id"], with_prices=True)
    print("Cache warm.\n")

    print("=" * 60)
    print("Approach A: Current (list + N sequential detail calls)")
    print("=" * 60)
    a_avg = benchmark("A", approach_a_current)

    print("=" * 60)
    print("Approach B: Batch (list + 1 parallel batch detail call)")
    print("=" * 60)
    b_avg = benchmark("B", approach_b_batch)

    print("=" * 60)
    print("Approach C: Enriched (1 call returns everything)")
    print("=" * 60)
    c_avg = benchmark("C", approach_c_enriched)

    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    fastest = min(a_avg, b_avg, c_avg)
    for label, avg in [("A (current)", a_avg), ("B (batch)", b_avg), ("C (enriched)", c_avg)]:
        marker = " << FASTEST" if avg == fastest else ""
        speedup = f"  ({a_avg / avg:.1f}x vs current)" if avg != a_avg else ""
        print(f"  {label}: {avg:.3f}s{speedup}{marker}")
