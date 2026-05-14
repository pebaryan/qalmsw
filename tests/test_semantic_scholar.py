"""Tests for Semantic Scholar retrieval module."""
from unittest.mock import patch

from qalmsw.retrieval import ScholarResult, search_by_title


def _mock_response(data: list[dict]) -> dict:
    return {"data": data}


def _paper(
    title: str = "Attention Is All You Need",
    authors: list[str] | None = None,
    year: int | None = 2017,
    abstract: str = "We propose the Transformer architecture.",
    arxiv_id: str = "1706.03762",
    url: str = "https://api.semanticscholar.org/CorpusID:1",
) -> dict:
    return {
        "title": title,
        "authors": [{"name": a} for a in (authors or ["Ashish Vaswani", "Noam Shazeer"])],
        "year": year,
        "abstract": abstract,
        "externalIds": {"ArXiv": arxiv_id} if arxiv_id else {},
        "url": url,
    }


def _mock_urlopen(json_data: dict):
    """Return a mock urlopen context manager."""
    import json as _json
    from unittest.mock import MagicMock

    cm = MagicMock()
    cm.__enter__.return_value.read.return_value = _json.dumps(json_data).encode("utf-8")
    return cm


def test_search_by_title_returns_first_match():
    data = _mock_response([_paper()])
    with patch("qalmsw.retrieval.semantic_scholar.urllib.request.urlopen",
               return_value=_mock_urlopen(data)):
        result = search_by_title("attention transformer")
    assert isinstance(result, ScholarResult)
    assert result.title == "Attention Is All You Need"
    assert result.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert result.year == 2017
    assert "Transformer" in result.abstract
    assert "semanticscholar" in (result.url or "")


def test_search_by_title_returns_none_when_no_results():
    data = _mock_response([])
    with patch("qalmsw.retrieval.semantic_scholar.urllib.request.urlopen",
               return_value=_mock_urlopen(data)):
        assert search_by_title("no such paper xyzzy") is None


def test_search_by_title_returns_none_on_http_error():
    import urllib.error

    def _raise(*args, **kwargs):
        raise urllib.error.HTTPError(
            "http://example.com", 429, "Too Many", {}, None
        )

    with patch("qalmsw.retrieval.semantic_scholar.urllib.request.urlopen", _raise):
        assert search_by_title("any title") is None


def test_missing_fields_produce_safe_defaults():
    data = _mock_response([
        _paper(
            title="", authors=None, year=None,
            abstract="", arxiv_id="", url="",
        )
    ])
    with patch("qalmsw.retrieval.semantic_scholar.urllib.request.urlopen",
               return_value=_mock_urlopen(data)):
        result = search_by_title("x")
    assert result is None  # empty title → None


def test_empty_title_returns_none():
    data = _mock_response([_paper(title="", authors=None)])
    with patch("qalmsw.retrieval.semantic_scholar.urllib.request.urlopen",
               return_value=_mock_urlopen(data)):
        assert search_by_title("x") is None


def test_exact_title_match_is_preferred():
    data = _mock_response([
        _paper(title="Some Related Work", year=2020),
        _paper(title="Attention Is All You Need", year=2017),
    ])
    with patch("qalmsw.retrieval.semantic_scholar.urllib.request.urlopen",
               return_value=_mock_urlopen(data)):
        result = search_by_title("Attention Is All You Need")
    assert result is not None
    assert result.title == "Attention Is All You Need"
    assert result.year == 2017
