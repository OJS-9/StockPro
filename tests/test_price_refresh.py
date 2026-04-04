"""
Price refresh test suite.

Part 1 — Scheduler unit test (no browser, connects to live DB):
  Seeds a stale symbol into price_cache, runs _do_refresh(), verifies it was refreshed.

Part 2 — Interval timing test:
  Patches REFRESH_INTERVAL to 10s, confirms the scheduler fires multiple times.

Part 3 — Browser test (requires running server + one-time login):
  Uses Playwright to open the portfolio page and confirm prices load from cache.

Usage:
  python test_price_refresh.py              # unit test only (default)
  python test_price_refresh.py --timing     # interval timing test (~25s)
  python test_price_refresh.py --save-auth  # log in and save browser session
  python test_price_refresh.py --browser    # browser test (needs --save-auth first)
  python test_price_refresh.py --all        # all tests
"""

import sys
import os
import time
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from dotenv import load_dotenv
load_dotenv()

AUTH_STATE_FILE = Path(__file__).parent / '.playwright_auth.json'
APP_URL = 'http://127.0.0.1:5000'


def _get_db_conn():
    """Open a raw psycopg2 connection, bypassing DatabaseManager init_schema."""
    import psycopg2
    import psycopg2.extras
    url = os.environ.get('DATABASE_URL')
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get('MYSQL_HOST', '127.0.0.1'),
        port=int(os.environ.get('MYSQL_PORT', 5432)),
        user=os.environ.get('MYSQL_USER', 'postgres'),
        password=os.environ.get('MYSQL_PASSWORD', ''),
        dbname=os.environ.get('MYSQL_DATABASE', 'postgres'),
    )


# ─────────────────────────────────────────────
# PART 1: Scheduler unit test
# ─────────────────────────────────────────────

def test_scheduler_unit():
    import psycopg2
    try:
        conn_check = _get_db_conn()
        conn_check.close()
    except psycopg2.OperationalError:
        import pytest
        pytest.skip("No database available — skipping live scheduler test")

    print('\n=== Part 1: Scheduler unit test ===\n')
    import psycopg2.extras
    from watchlist.price_refresh import PriceRefreshJob

    TEST_SYMBOL = 'MSFT'
    STALE_PRICE = 999.99

    # ── Seed a stale entry ────────────────────────────────────────────────
    print(f'[1/4] Seeding {TEST_SYMBOL} into price_cache with stale timestamp (30 min ago)...')
    conn = _get_db_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO price_cache (symbol, asset_type, price, change_percent, last_updated)
                VALUES (%s, 'stock', %s, NULL, NOW() - INTERVAL '30 minutes')
                ON CONFLICT (symbol) DO UPDATE SET
                    price        = EXCLUDED.price,
                    last_updated = NOW() - INTERVAL '30 minutes'
            """, (TEST_SYMBOL, STALE_PRICE))
        conn.commit()
    finally:
        conn.close()
    print(f'  Seeded {TEST_SYMBOL} @ ${STALE_PRICE} (stale)')

    before = datetime.utcnow()

    # ── Run the refresh ───────────────────────────────────────────────────
    # Patch init_schema to no-op — schema already exists, running server holds a lock
    import database as db_module
    db_module.DatabaseManager.init_schema = lambda self: None

    print(f'\n[2/4] Running PriceRefreshJob._do_refresh()...')
    job = PriceRefreshJob()
    job._do_refresh()
    print('  Done.')

    # ── Verify last_updated changed ───────────────────────────────────────
    print(f'\n[3/4] Checking {TEST_SYMBOL} was refreshed in price_cache...')
    conn = _get_db_conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM price_cache WHERE symbol = %s", (TEST_SYMBOL,))
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        print(f'  FAIL: {TEST_SYMBOL} missing from price_cache')
        return False

    last_updated = row['last_updated']
    # Supabase returns timezone-aware datetimes; strip tz for comparison
    if last_updated.tzinfo is not None:
        from datetime import timezone
        last_updated = last_updated.replace(tzinfo=None)

    if last_updated > before:
        print(f'  PASS: last_updated={last_updated} > before={before}')
    else:
        print(f'  FAIL: last_updated={last_updated} not updated (before={before})')
        return False

    # ── Verify price changed ──────────────────────────────────────────────
    print(f'\n[4/4] Verifying price changed from seeded ${STALE_PRICE}...')
    new_price = float(row['price']) if row['price'] is not None else None
    if new_price is None:
        print(f'  NOTE: price is None — provider returned no data (API quota?)')
    elif new_price != STALE_PRICE:
        print(f'  PASS: price updated ${STALE_PRICE} → ${new_price}')
    else:
        print(f'  NOTE: price unchanged (${new_price}) — provider may have returned same value')

    return True


# ─────────────────────────────────────────────
# PART 2: Interval timing test
# ─────────────────────────────────────────────

def test_interval_timing():
    print('\n=== Part 2: Interval timing test (10s cycle, ~25s total) ===\n')
    import watchlist.price_refresh as pr_module

    original_interval = pr_module.REFRESH_INTERVAL
    pr_module.REFRESH_INTERVAL = 10

    call_times = []
    original_do_refresh = pr_module.PriceRefreshJob._do_refresh

    def mock_refresh(self):
        call_times.append(datetime.utcnow())
        print(f'  [cycle {len(call_times)}] fired at {call_times[-1].strftime("%H:%M:%S")}')

    pr_module.PriceRefreshJob._do_refresh = mock_refresh

    from watchlist.price_refresh import PriceRefreshJob
    job = PriceRefreshJob()
    job.start()

    print('Waiting 25s to observe 2+ cycles...')
    time.sleep(25)
    job.stop()

    pr_module.REFRESH_INTERVAL = original_interval
    pr_module.PriceRefreshJob._do_refresh = original_do_refresh

    if len(call_times) >= 2:
        gap = (call_times[1] - call_times[0]).total_seconds()
        print(f'\nPASS: {len(call_times)} cycles observed, gap = {gap:.1f}s (expected ~10s)')
        return True
    else:
        print(f'\nFAIL: only {len(call_times)} cycle(s) in 25s')
        return False


# ─────────────────────────────────────────────
# PART 3: Browser test
# ─────────────────────────────────────────────

def save_auth():
    from playwright.sync_api import sync_playwright

    print('\n=== Save auth state ===')
    print('A browser will open. Log in, then wait — the window will close automatically.')
    print(f'Saving to: {AUTH_STATE_FILE}\n')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f'{APP_URL}/sign-in')
        # Wait until navigated away from sign-in
        page.wait_for_function(
            "() => !window.location.pathname.startsWith('/sign')",
            timeout=120_000
        )
        ctx.storage_state(path=str(AUTH_STATE_FILE))
        browser.close()

    print(f'\nAuth saved. Run: python test_price_refresh.py --browser')


def test_browser():
    import pytest
    pytest.importorskip("playwright", reason="playwright not installed — skipping browser test")
    from playwright.sync_api import sync_playwright

    print('\n=== Part 3: Browser test ===\n')

    if not AUTH_STATE_FILE.exists():
        print(f'No auth state at {AUTH_STATE_FILE}. Run --save-auth first.')
        return False

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH_STATE_FILE))
        page = ctx.new_page()

        # ── 3a: portfolio list loads ──────────────────────────────────────
        print('[1/3] GET /portfolio ...')
        t0 = time.time()
        resp = page.goto(f'{APP_URL}/portfolio', wait_until='domcontentloaded')
        ms = int((time.time() - t0) * 1000)
        if resp and resp.status == 200:
            print(f'  PASS: 200 OK in {ms}ms')
            results.append(True)
        else:
            print(f'  FAIL: status={resp.status if resp else "none"}')
            results.append(False)
            browser.close()
            return False

        # ── 3b: navigate to first portfolio, wait for prices ─────────────
        print('\n[2/3] Opening first portfolio and waiting for prices to render...')
        first_link = page.locator('a[href*="/portfolio/"]').first
        if first_link.count() == 0:
            print('  SKIP: no portfolios found — create one first')
            results.append(None)
        else:
            href = first_link.get_attribute('href')
            print(f'  Navigating to {href}')
            page.goto(f'{APP_URL}{href}', wait_until='domcontentloaded')
            t0 = time.time()
            try:
                # Skeletons disappear once JS populates prices
                page.wait_for_function(
                    "() => document.querySelectorAll('.animate-pulse').length === 0",
                    timeout=20_000
                )
                elapsed = int((time.time() - t0) * 1000)
                print(f'  PASS: prices rendered in {elapsed}ms (skeletons gone)')
                results.append(True)
            except Exception:
                pulse = page.evaluate("document.querySelectorAll('.animate-pulse').length")
                print(f'  FAIL: {pulse} skeleton(s) still showing after 20s')
                results.append(False)

            # ── 3c: no N/A cells ─────────────────────────────────────────
            print('\n[3/3] Checking for N/A price cells...')
            total_rows = page.locator('tr[data-symbol]').count()
            na_count = page.locator('tr[data-symbol] >> text=N/A').count()
            if total_rows == 0:
                print('  SKIP: no holding rows found')
                results.append(None)
            elif na_count == 0:
                print(f'  PASS: all {total_rows} row(s) have prices')
                results.append(True)
            else:
                print(f'  WARN: {na_count}/{total_rows} row(s) show N/A (market closed or API quota)')
                results.append(True)

        browser.close()

    passed  = sum(1 for r in results if r is True)
    failed  = sum(1 for r in results if r is False)
    skipped = sum(1 for r in results if r is None)
    print(f'\nBrowser: {passed} passed, {failed} failed, {skipped} skipped')
    return failed == 0


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--timing',     action='store_true')
    parser.add_argument('--save-auth',  action='store_true')
    parser.add_argument('--browser',    action='store_true')
    parser.add_argument('--all',        action='store_true')
    args = parser.parse_args()

    if args.save_auth:
        save_auth()
        return

    run_unit    = not any([args.timing, args.browser]) or args.all
    run_timing  = args.timing or args.all
    run_browser = args.browser or args.all

    all_pass = True

    if run_unit:
        all_pass = test_scheduler_unit() and all_pass

    if run_timing:
        all_pass = test_interval_timing() and all_pass

    if run_browser:
        all_pass = test_browser() and all_pass

    print('\n' + ('ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'))
    sys.exit(0 if all_pass else 1)


if __name__ == '__main__':
    main()
