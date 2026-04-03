"""
News briefing service — fetches financial articles via Nimble agents (Bloomberg + Morningstar + WSJ)
as primary source, and web search (WSJ + Reuters) as secondary on demand.
Results are cached in memory with a 15-minute TTL per cache slot.
"""

import time
import urllib.parse
from typing import List, Dict

CACHE_TTL = 15 * 60  # 15 minutes

BLOOMBERG_AGENT = "bloomberg_search_2026_02_23_a9u4p1tv_1184e640"
MORNINGSTAR_AGENT = "morningstar_search_2026_02_23_zicq0zdj_02869390"
WSJ_AGENT = "wsj_article_template_2026_03_02_z7hhhvxe"
WSJ_PIPELINE = "WSJcomUSBusiness"
SEARCH_QUERY = "markets stocks economy finance"

_cache = {
    "primary": {"articles": [], "fetched_at": None},
    "more": {"articles": [], "fetched_at": None},
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
    morningstar_results = client.run_agent(
        MORNINGSTAR_AGENT, {"search_term": SEARCH_QUERY}
    )
    wsj_results = client.run_agent(WSJ_AGENT, {"feed_name": WSJ_PIPELINE})

    # Sort each source by image presence before interleaving, so image articles
    # lead within each source without collapsing all no-image sources to the end.
    def _sort_by_image(items, publisher):
        mapped = [_map_article(item, publisher) for item in items]
        mapped.sort(key=lambda a: 0 if a["image"] else 1)
        return mapped

    sources = [
        _sort_by_image(bloomberg_results, "Bloomberg"),
        _sort_by_image(morningstar_results, "Morningstar"),
        _sort_by_image(wsj_results, "WSJ"),
    ]

    # Round-robin interleave: Bloomberg → Morningstar → WSJ
    indices = [0, 0, 0]
    interleaved = []
    while True:
        added = False
        for i, items in enumerate(sources):
            if indices[i] < len(items):
                interleaved.append(items[indices[i]])
                indices[i] += 1
                added = True
        if not added:
            break

    _cache["primary"]["articles"] = interleaved
    _cache["primary"]["fetched_at"] = time.time()


def _map_article(item: Dict, publisher: str) -> Dict:
    headline = item.get("headline", item.get("header", item.get("title", ""))).strip()
    article_url = item.get("article_url", "").strip()
    if not article_url:
        if publisher == "Bloomberg":
            encoded = urllib.parse.urlencode({"query": headline})
            article_url = f"https://www.bloomberg.com/search?{encoded}"
        elif publisher == "WSJ":
            encoded = urllib.parse.urlencode({"query": headline})
            article_url = f"https://www.wsj.com/search?{encoded}"
        else:
            encoded = urllib.parse.urlencode({"q": headline})
            article_url = f"https://www.morningstar.com/search?{encoded}"

    return {
        "title": headline,
        "description": item.get("summary", item.get("description", "")).strip(),
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
        {
            "name": "WSJ",
            "query": "site:wsj.com markets stocks earnings economy finance",
        },
        {
            "name": "Reuters",
            "query": "site:reuters.com markets stocks earnings economy finance",
        },
    ]

    articles = []
    for source in secondary_sources:
        try:
            result = client.search(source["query"], num_results=10, topic="news")
            results = result.get("results") or []
            for item in results:
                title = item.get("title", "").strip()
                url = item.get("url", "").strip()
                if title and url:
                    articles.append(
                        {
                            "title": title,
                            "description": item.get("description", "").strip(),
                            "image": "",
                            "category": "Markets",
                            "publisher": source["name"],
                            "url": url,
                        }
                    )
        except Exception:
            continue

    _cache["more"]["articles"] = articles
    _cache["more"]["fetched_at"] = time.time()
