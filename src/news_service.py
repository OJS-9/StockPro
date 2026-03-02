"""
News briefing service — fetches financial articles via Nimble agents (Bloomberg + Morningstar)
as primary source, and web search (WSJ + Reuters) as secondary on demand.
Results are cached in memory with a 15-minute TTL per cache slot.
"""

import time
import urllib.parse
from typing import List, Dict

CACHE_TTL = 15 * 60  # 15 minutes

BLOOMBERG_AGENT = "bloomberg_search_2026_02_23_a9u4p1tv_1184e640"
MORNINGSTAR_AGENT = "morningstar_search_2026_02_23_zicq0zdj_02869390"
SEARCH_QUERY = "markets stocks economy finance"

_cache = {
    "primary": {"articles": [], "fetched_at": None},
    "more":    {"articles": [], "fetched_at": None},
}


def get_briefing() -> List[Dict]:
    now = time.time()
    slot = _cache["primary"]
    if slot["fetched_at"] is None or (now - slot["fetched_at"]) > CACHE_TTL:
        _refresh_primary()
    return _cache["primary"]["articles"]


def get_more() -> List[Dict]:
    now = time.time()
    slot = _cache["more"]
    if slot["fetched_at"] is None or (now - slot["fetched_at"]) > CACHE_TTL:
        _refresh_more()
    return _cache["more"]["articles"]


def _refresh_primary() -> None:
    try:
        from nimble_client import NimbleClient
        client = NimbleClient()
    except Exception:
        return

    bloomberg_results = client.run_agent(BLOOMBERG_AGENT, {"query": SEARCH_QUERY})
    morningstar_results = client.run_agent(MORNINGSTAR_AGENT, {"search_term": SEARCH_QUERY})

    # Interleave: bloomberg[0], morningstar[0], bloomberg[1] → first 3
    interleaved = []
    b_idx = m_idx = 0
    toggle = True
    while len(interleaved) < 3 and (b_idx < len(bloomberg_results) or m_idx < len(morningstar_results)):
        if toggle and b_idx < len(bloomberg_results):
            interleaved.append((_map_article(bloomberg_results[b_idx], "Bloomberg"), "bloomberg"))
            b_idx += 1
        elif not toggle and m_idx < len(morningstar_results):
            interleaved.append((_map_article(morningstar_results[m_idx], "Morningstar"), "morningstar"))
            m_idx += 1
        elif b_idx < len(bloomberg_results):
            interleaved.append((_map_article(bloomberg_results[b_idx], "Bloomberg"), "bloomberg"))
            b_idx += 1
        elif m_idx < len(morningstar_results):
            interleaved.append((_map_article(morningstar_results[m_idx], "Morningstar"), "morningstar"))
            m_idx += 1
        toggle = not toggle

    _cache["primary"]["articles"] = [a for a, _ in interleaved]
    _cache["primary"]["fetched_at"] = time.time()


def _map_article(item: Dict, publisher: str) -> Dict:
    headline = item.get("headline", item.get("title", "")).strip()
    article_url = item.get("article_url", "").strip()
    if not article_url:
        encoded = urllib.parse.urlencode({"query" if publisher == "Bloomberg" else "q": headline})
        base = "https://www.bloomberg.com/search" if publisher == "Bloomberg" else "https://www.morningstar.com/search"
        article_url = f"{base}?{encoded}"

    return {
        "title": headline,
        "description": item.get("summary", "").strip(),
        "image": item.get("image_url", ""),
        "category": item.get("category", "Markets"),
        "publisher": publisher,
        "url": article_url,
    }


def _refresh_more() -> None:
    try:
        from nimble_client import NimbleClient
        client = NimbleClient()
    except Exception:
        return

    secondary_sources = [
        {"name": "WSJ",     "query": "site:wsj.com markets stocks earnings economy finance"},
        {"name": "Reuters", "query": "site:reuters.com markets stocks earnings economy finance"},
    ]

    articles = []
    for source in secondary_sources:
        try:
            result = client.search(source["query"], num_results=2, topic="news")
            results = result.get("results") or []
            for item in results:
                title = item.get("title", "").strip()
                url = item.get("url", "").strip()
                if title and url:
                    articles.append({
                        "title": title,
                        "description": item.get("description", "").strip(),
                        "image": "",
                        "category": "Markets",
                        "publisher": source["name"],
                        "url": url,
                    })
                    break
        except Exception:
            continue

    _cache["more"]["articles"] = articles
    _cache["more"]["fetched_at"] = time.time()
