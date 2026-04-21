from unittest.mock import patch

from qalmsw.retrieval import ScholarResult, search_by_title


def _fake_pub(**bib_overrides) -> dict:
    bib = {
        "title": "Attention Is All You Need",
        "author": ["Ashish Vaswani", "Noam Shazeer"],
        "pub_year": "2017",
        "abstract": "We propose a new architecture, the Transformer.",
    }
    bib.update(bib_overrides)
    return {"bib": bib, "pub_url": "https://arxiv.org/abs/1706.03762"}


def test_search_by_title_returns_first_match():
    with patch(
        "qalmsw.retrieval.scholar.scholarly.search_pubs", return_value=iter([_fake_pub()])
    ):
        result = search_by_title("attention transformer")
    assert isinstance(result, ScholarResult)
    assert result.title == "Attention Is All You Need"
    assert result.authors == ["Ashish Vaswani", "Noam Shazeer"]
    assert result.year == 2017
    assert "Transformer" in result.abstract
    assert result.url == "https://arxiv.org/abs/1706.03762"


def test_search_by_title_returns_none_when_no_results():
    with patch("qalmsw.retrieval.scholar.scholarly.search_pubs", return_value=iter([])):
        assert search_by_title("no such paper xyzzy") is None


def test_author_string_is_split_on_and():
    raw = _fake_pub(author="Ashish Vaswani and Noam Shazeer and Niki Parmar")
    with patch("qalmsw.retrieval.scholar.scholarly.search_pubs", return_value=iter([raw])):
        result = search_by_title("x")
    assert result is not None
    assert result.authors == ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar"]


def test_missing_fields_produce_safe_defaults():
    raw = {"bib": {}}
    with patch("qalmsw.retrieval.scholar.scholarly.search_pubs", return_value=iter([raw])):
        result = search_by_title("x")
    assert result is not None
    assert result.title == ""
    assert result.authors == []
    assert result.year is None
    assert result.abstract == ""
    assert result.url is None


def test_non_numeric_year_coerces_to_none():
    raw = _fake_pub(pub_year="in press")
    with patch("qalmsw.retrieval.scholar.scholarly.search_pubs", return_value=iter([raw])):
        result = search_by_title("x")
    assert result is not None
    assert result.year is None


def test_eprint_url_used_when_pub_url_missing():
    raw = _fake_pub()
    raw.pop("pub_url")
    raw["eprint_url"] = "https://example.org/eprint.pdf"
    with patch("qalmsw.retrieval.scholar.scholarly.search_pubs", return_value=iter([raw])):
        result = search_by_title("x")
    assert result is not None
    assert result.url == "https://example.org/eprint.pdf"
