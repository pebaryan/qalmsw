"""Semantic Scholar retrieval via the free API.

Replaces Google Scholar scraping (`scholarly`) for the claims checker.
Semantic Scholar has a free, no-auth-required API with generous rate limits.

API:
    GET /graph/v1/paper/search?query={title}&limit=3
    &fields=title,authors,year,abstract,externalIds,url

Docs:
    https://api.semanticscholar.org/api-docs/graph
    #tag/Paper-Data/operation/get_graph_search_papers

Rate limit: ~1 req/sec for free tier. We throttle to one per second.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from qalmsw.retrieval.scholar import ScholarResult

_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
_FIELDS = "title,authors,year,abstract,externalIds,url"
_USER_AGENT = "qalmsw/0.0.1"

_last_call = 0.0


def search_by_title(title: str) -> ScholarResult | None:
    """Return the first Semantic Scholar match for ``title``, or ``None``.

    Uses stdlib only (no external deps). Throttled to 1 req/sec.
    """
    global _last_call

    encoded = urllib.parse.quote(title)
    url = f"{_SEARCH_URL}?query={encoded}&limit=3&fields={_FIELDS}"

    # Rate limit: at least 1 second between calls
    now = time.time()
    elapsed = now - _last_call
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        _last_call = time.time()
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, OSError):
        _last_call = time.time()
        return None

    results = data.get("data", [])
    if not results:
        return None

    best = _pick_best(results, title)
    if best is None:
        return None
    return _to_result(best)


def _pick_best(results: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    """Return the best match from a list of results.

    Tries exact title match first (case-insensitive), then falls back to first result.
    """
    query_lower = query.lower().strip()
    for r in results:
        candidate = (r.get("title") or "").lower().strip()
        if candidate == query_lower:
            return r
    # Fall back to first result
    return results[0]


def _to_result(raw: dict[str, Any]) -> ScholarResult | None:
    """Convert a Semantic Scholar API response to a ScholarResult."""
    title = _coerce_str(raw.get("title"))
    if not title:
        return None

    authors_raw = raw.get("authors") or []
    authors = [a.get("name", "") for a in authors_raw if a.get("name")]

    abstract = _coerce_str(raw.get("abstract"))
    year = _coerce_year(raw.get("year"))

    # Prefer Semantic Scholar URL, fall back to external IDs
    url = raw.get("url") or ""
    external_ids = raw.get("externalIds") or {}
    if not url:
        url = external_ids.get("ArXiv", "") or external_ids.get("DOI", "")

    return ScholarResult(
        title=title,
        authors=authors,
        year=year,
        abstract=abstract,
        url=url or None,
    )


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
