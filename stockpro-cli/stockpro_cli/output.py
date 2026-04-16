"""JSON vs pretty output formatting."""

import json
import sys


def output(data, pretty: bool = False):
    if not pretty:
        json.dump(data, sys.stdout)
        sys.stdout.write("\n")
        return

    if isinstance(data, dict):
        # Portfolio list response
        if "portfolios" in data:
            _print_portfolios(data)
            return
        # Alerts list
        if "alerts" in data and isinstance(data["alerts"], list):
            _print_alerts(data["alerts"])
            return
        # Watchlist response (active_watchlist or watchlists)
        if "active_watchlist" in data:
            _print_watchlist_active(data["active_watchlist"])
            return
        if "watchlists" in data:
            for wl in data["watchlists"]:
                _print_watchlist_active(wl)
            return
        # Notifications
        if "notifications" in data:
            _print_notifications(data["notifications"])
            return
        # Reports list
        if "reports" in data and isinstance(data["reports"], list):
            _print_reports(data["reports"])
            if "current_page" in data:
                print(f"\nPage {data['current_page']}")
            return
        # Auth status
        if "profile" in data:
            p = data["profile"]
            print(f"User:  {p.get('display_name', '?')}")
            print(f"Tier:  {p.get('tier', '?')}")
            print(f"ID:    {p.get('user_id', '?')}")
            if "preferences" in data:
                print(f"Lang:  {data['preferences'].get('language', '?')}")
            return
        # Home dashboard
        if "holdings_preview" in data or "news" in data:
            _print_home(data)
            return
        # Ticker recent (simple list of strings)
        if "tickers" in data and isinstance(data["tickers"], list):
            for t in data["tickers"]:
                print(f"  {t}")
            return
        # Usage
        if "reports_used" in data:
            _print_usage(data)
            return
        # News response
        if "articles" in data or (isinstance(data.get("news"), list)):
            _print_news(data.get("articles") or data.get("news", []))
            return
        # Generic dict
        _print_dict_generic(data)
    elif isinstance(data, list):
        # News articles list (has title + publisher keys)
        if data and isinstance(data[0], dict) and "title" in data[0] and "publisher" in data[0]:
            _print_news(data)
            return
        _print_table_auto(data)
    else:
        print(data)


def _print_portfolios(data):
    for p in data.get("portfolios", []):
        pid = p.get("portfolio_id", "?")[:8]
        total = p.get("total_market_value", 0)
        gain = p.get("total_unrealized_gain", 0)
        gain_pct = p.get("total_unrealized_gain_pct", 0)
        sign = "+" if gain >= 0 else ""
        print(f"Portfolio {pid}...  ${total:,.2f}  {sign}${gain:,.2f} ({sign}{gain_pct:.1f}%)")
        print()

        holdings = p.get("holdings", [])
        if not holdings:
            print("  (no holdings)")
            continue

        print(f"  {'Symbol':<8} {'Price':>10} {'Shares':>8} {'Value':>12} {'P&L':>12} {'P&L %':>8}")
        print(f"  {'------':<8} {'-----':>10} {'------':>8} {'-----':>12} {'---':>12} {'-----':>8}")

        for h in sorted(holdings, key=lambda x: x.get("market_value", 0), reverse=True):
            sym = h.get("symbol", "?")
            price = h.get("current_price", 0)
            qty = h.get("total_quantity", 0)
            mv = h.get("market_value", 0)
            ug = h.get("unrealized_gain", 0)
            ugp = h.get("unrealized_gain_pct", 0)
            sign = "+" if ug >= 0 else ""
            print(f"  {sym:<8} ${price:>9.2f} {qty:>8.2f} ${mv:>11,.2f} {sign}${ug:>10,.2f} {sign}{ugp:>6.1f}%")

        print()

    totals = data.get("totals", {})
    if totals:
        tv = totals.get("total_value", 0)
        tp = totals.get("total_pnl", 0)
        sign = "+" if tp >= 0 else ""
        print(f"  Total: ${tv:,.2f}  {sign}${tp:,.2f}")


def _print_alerts(alerts):
    if not alerts:
        print("(no alerts)")
        return
    print(f"  {'Symbol':<8} {'Dir':<6} {'Target':>10} {'Current':>10} {'Active':>7}  {'ID'}")
    print(f"  {'------':<8} {'---':<6} {'------':>10} {'-------':>10} {'------':>7}  {'--'}")
    for a in alerts:
        sym = a.get("symbol", "?")
        d = a.get("direction", "?")
        tp = a.get("target_price", 0)
        cp = a.get("current_price", 0)
        active = "yes" if a.get("active") else "no"
        aid = a.get("alert_id", a.get("id", "?"))[:8]
        print(f"  {sym:<8} {d:<6} ${tp:>9.2f} ${cp:>9.2f} {active:>7}  {aid}...")


def _print_watchlist_active(wl):
    if not wl:
        print("(no watchlist)")
        return
    name = wl.get("name", "Watchlist")
    wid = str(wl.get("watchlist_id", wl.get("id", "?")))[:8]
    print(f"\n{name} ({wid}...)")

    items = wl.get("items", [])
    if not items:
        print("  (empty)")
        return

    print(f"  {'Symbol':<8} {'Price':>10} {'Change':>8}  {'Pinned'}")
    print(f"  {'------':<8} {'-----':>10} {'------':>8}  {'------'}")
    for item in items:
        sym = item.get("symbol", "?")
        price = float(item.get("price", 0))
        change = float(item.get("change_pct", 0))
        pinned = "yes" if item.get("is_pinned") else ""
        sign = "+" if change >= 0 else ""
        print(f"  {sym:<8} ${price:>9.2f} {sign}{change:>6.1f}%  {pinned}")


def _print_news(articles):
    if not articles:
        print("(no news)")
        return
    for a in articles:
        title = a.get("title", "")
        pub = a.get("publisher", "")
        sentiment = a.get("sentiment", "")
        if len(title) > 65:
            title = title[:62] + "..."
        sent_tag = f" [{sentiment}]" if sentiment and sentiment != "neutral" else ""
        print(f"  {pub:<14} {title}{sent_tag}")


def _print_notifications(notifications):
    if not notifications:
        print("(no notifications)")
        return
    for n in notifications:
        read = "read" if n.get("read_at") else "NEW"
        msg = n.get("body", n.get("message", ""))
        sym = n.get("symbol", "")
        ts = _short_date(n.get("created_at", ""))
        print(f"  [{read:>4}] {ts}  {sym:<6} {msg}")


def _print_reports(reports):
    if not reports:
        print("(no reports)")
        return
    print(f"  {'Ticker':<8} {'Type':<14} {'Date':<12} {'ID'}")
    print(f"  {'------':<8} {'----':<14} {'----':<12} {'--'}")
    for r in reports:
        ticker = r.get("ticker", "?")
        tt = r.get("trade_type", "?")
        ts = _short_date(r.get("created_at", ""))
        rid = r.get("report_id", r.get("id", "?"))[:8]
        print(f"  {ticker:<8} {tt:<14} {ts:<12} {rid}...")


def _print_home(data):
    # Holdings preview
    holdings = data.get("holdings_preview", [])
    if holdings:
        print("Portfolio")
        print(f"  {'Symbol':<8} {'Price':>10} {'Value':>12} {'P&L':>12} {'P&L %':>8}")
        print(f"  {'------':<8} {'-----':>10} {'-----':>12} {'---':>12} {'-----':>8}")
        for h in holdings:
            sym = h.get("symbol", "?")
            mv = h.get("market_value", 0)
            ug = h.get("unrealized_gain", 0)
            ugp = h.get("unrealized_gain_pct", 0)
            avg = h.get("average_cost", 0)
            sign = "+" if ug >= 0 else ""
            print(f"  {sym:<8} ${avg:>9.2f} ${mv:>11,.2f} {sign}${ug:>10,.2f} {sign}{ugp:>6.1f}%")
        print()

    # Watchlist preview
    wl_items = data.get("watchlist_preview", [])
    if wl_items:
        print("Watchlist")
        for item in wl_items:
            sym = item.get("symbol", "?")
            name = item.get("name", "")
            price = float(item.get("price", 0))
            change = float(item.get("change_pct", 0))
            sign = "+" if change >= 0 else ""
            print(f"  {sym:<8} ${price:>9.2f}  {sign}{change:.1f}%  {name}")
        print()

    # News
    news = data.get("news", [])
    if news:
        print("News")
        for n in news[:5]:
            title = n.get("title", "")
            pub = n.get("publisher", "")
            if len(title) > 60:
                title = title[:57] + "..."
            print(f"  {pub:<14} {title}")
        print()

    # Recent reports
    reports = data.get("recent_reports", [])
    if reports:
        print("Recent Reports")
        for r in reports[:5]:
            ticker = r.get("ticker", "?")
            tt = r.get("trade_type", "?")
            ts = _short_date(r.get("created_at", ""))
            print(f"  {ticker:<8} {tt:<14} {ts}")
        print()

    # Alerts count
    ac = data.get("active_alerts_count")
    if ac is not None:
        print(f"Active alerts: {ac}")


def _print_usage(data):
    print(f"Tier:    {'Pro' if data.get('is_pro') else 'Free'}")
    print(f"Period:  {data.get('period', '?')}")
    used = data.get("reports_used", 0)
    limit = data.get("reports_limit")
    if limit:
        print(f"Reports: {used}/{limit}")
    else:
        print(f"Reports: {used} (unlimited)")


def _print_dict_generic(data):
    """Fallback for unknown dict shapes."""
    for k, v in data.items():
        if isinstance(v, (list, dict)):
            continue
        print(f"{k}: {v}")
    for k, v in data.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            print(f"\n--- {k} ---")
            _print_table_auto(v)


def _print_table_auto(rows):
    """Print a list of dicts, auto-selecting non-nested columns."""
    if not rows:
        print("(empty)")
        return
    keys = [k for k in rows[0] if not isinstance(rows[0][k], (list, dict))]
    _print_rows(rows, keys)


def _print_rows(rows, keys):
    if not keys:
        print("(no displayable columns)")
        return
    widths = {}
    for k in keys:
        col_w = len(str(k))
        for r in rows:
            col_w = max(col_w, len(str(r.get(k, ""))))
        widths[k] = min(col_w, 40)

    header = "  ".join(str(k).ljust(widths[k]) for k in keys)
    sep = "  ".join("-" * widths[k] for k in keys)
    print(header)
    print(sep)
    for r in rows:
        vals = []
        for k in keys:
            v = str(r.get(k, ""))
            if len(v) > 40:
                v = v[:37] + "..."
            vals.append(v.ljust(widths[k]))
        print("  ".join(vals))


def _short_date(ts: str) -> str:
    """Turn ISO timestamp into YYYY-MM-DD."""
    if not ts:
        return "?"
    return ts[:10]
