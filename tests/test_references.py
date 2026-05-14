"""Tests for the Reference Validation Checker."""
from pathlib import Path
from typing import Any

from qalmsw.bib import BibEntry
from qalmsw.checkers import ReferenceChecker, Severity
from qalmsw.document import Document


def _doc() -> Document:
    return Document(path=Path("paper.tex"), source="", paragraphs=[])


def _entry(
    key: str,
    *,
    title: str = "A Real Paper",
    eprint: str = "",
    doi: str = "",
    line: int = 1,
) -> BibEntry:
    return BibEntry(
        key=key,
        entry_type="article",
        file=Path("refs.bib"),
        line=line,
        title=title,
        eprint=eprint,
        doi=doi,
    )


def _make_verify(exists_map: dict[str, bool]) -> Any:
    """Create a verify function that returns hardcoded results by bib key."""
    def verify(entry: BibEntry) -> tuple[bool, str] | None:
        eprint_raw = (entry.eprint or "").strip()
        doi_raw = (entry.doi or "").strip()
        if eprint_raw:
            exists = exists_map.get(entry.key, False)
            return (exists, "Test title") if exists else (False, "arXiv test error")
        if doi_raw:
            exists = exists_map.get(entry.key, False)
            return (exists, "https://doi.org/test") if exists else (False, "DOI test error")
        return None
    return verify


def test_arxiv_entry_exists():
    """An arXiv entry that resolves is silent."""
    entry = _entry("real2024", eprint="2401.12345")
    checker = ReferenceChecker([entry], verify=_make_verify({"real2024": True}))
    findings = checker.check(_doc())
    assert findings == []


def test_arxiv_entry_not_found():
    """An arXiv entry that doesn't resolve is an error."""
    entry = _entry("ghost2024", eprint="2401.99999")
    checker = ReferenceChecker([entry], verify=_make_verify({"ghost2024": False}))
    findings = checker.check(_doc())
    errors = [f for f in findings if f.severity == Severity.error]
    assert len(errors) >= 1
    assert "arXiv" in errors[0].message
    assert "ghost2024" in errors[0].message


def test_doi_entry_exists():
    """A DOI entry that resolves is silent."""
    entry = _entry("real2024", doi="10.1234/example")
    checker = ReferenceChecker([entry], verify=_make_verify({"real2024": True}))
    findings = checker.check(_doc())
    assert findings == []


def test_doi_entry_not_found():
    """A DOI entry that doesn't resolve is an error."""
    entry = _entry("ghost2024", doi="10.9999/nonexistent")
    checker = ReferenceChecker([entry], verify=_make_verify({"ghost2024": False}))
    findings = checker.check(_doc())
    errors = [f for f in findings if f.severity == Severity.error]
    assert len(errors) >= 1
    assert "DOI" in errors[0].message
    assert "ghost2024" in errors[0].message


def test_no_arxiv_or_doi_is_silent():
    """Entries without arXiv or DOI produce no finding (can't verify, nothing actionable)."""
    entry = _entry("bare2024", title="Some Paper")
    checker = ReferenceChecker([entry], verify=_make_verify({}))
    findings = checker.check(_doc())
    assert findings == []


def test_arxiv_priority_over_doi():
    """When both eprint and doi exist, arXiv is checked first."""
    entry = _entry("dual2024", eprint="2401.12345", doi="10.1234/example")
    # Verify function returns True for arXiv check
    checker = ReferenceChecker([entry], verify=_make_verify({"dual2024": True}))
    findings = checker.check(_doc())
    assert findings == []


def test_cache_prevents_duplicate_checks():
    """Same key checked once regardless of duplicate entries."""
    entry_a = _entry("same2024", eprint="2401.12345", line=1)
    entry_b = _entry("same2024", eprint="2401.12345", line=2)
    call_count = 0

    def verify(entry: BibEntry) -> tuple[bool, str] | None:
        nonlocal call_count
        call_count += 1
        return (True, "Paper title")

    checker = ReferenceChecker([entry_a, entry_b], verify=verify)
    checker.check(_doc())
    assert call_count == 1  # Only one call despite two entries with same key