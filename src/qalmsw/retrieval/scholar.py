"""Google Scholar retrieval via the `scholarly` library.

Google Scholar has no official API. `scholarly` scrapes the public search pages and
works fine for interactive, small-volume use on a personal machine — which is the
expected context for ``qalmsw``. Scaled-up use (CI, bulk verification) will hit
CAPTCHAs and silent blocks; for that, switch to Semantic Scholar or arXiv.

This module is deliberately minimal — it returns the first plausible match for a
title query as a ``ScholarResult``. The upcoming ``claims`` checker will:
  1. Look a citation key up in the .bib to get a title.
  2. Call ``search_by_title(title)`` to get an abstract/URL.
  3. Hand (claim, abstract) to the LLM judge.

Interactive use:
    qalmsw scholar "Attention is all you need"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scholarly import scholarly


@dataclass(frozen=True)
class ScholarResult:
    title: str
    authors: list[str]
    year: int | None
    abstract: str
    url: str | None


def search_by_title(title: str) -> ScholarResult | None:
    """Return the first Google Scholar result for ``title``, or ``None`` if no match.

    Network call; raises whatever ``scholarly`` raises on upstream failure.
    """
    try:
        first = next(scholarly.search_pubs(title))
    except StopIteration:
        return None
    return _to_result(first)


def _to_result(raw: dict[str, Any]) -> ScholarResult:
    bib = raw.get("bib", {}) or {}
    return ScholarResult(
        title=_coerce_str(bib.get("title")),
        authors=_coerce_authors(bib.get("author")),
        year=_coerce_year(bib.get("pub_year")),
        abstract=_coerce_str(bib.get("abstract")),
        url=raw.get("pub_url") or raw.get("eprint_url"),
    )


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_authors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(a).strip() for a in value if str(a).strip()]
    return [part.strip() for part in str(value).split(" and ") if part.strip()]


def _coerce_year(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


