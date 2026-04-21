from pathlib import Path

from qalmsw.bib import BibEntry
from qalmsw.checkers import CitationChecker, Severity
from qalmsw.document import Document


def _doc(source: str) -> Document:
    return Document(path=Path("paper.tex"), source=source, paragraphs=[])


def _entry(key: str, line: int = 1, file: str = "refs.bib") -> BibEntry:
    return BibEntry(key=key, entry_type="article", file=Path(file), line=line)


def test_missing_cite_key_is_error():
    doc = _doc("Hello \\cite{ghost} world\n")
    findings = CitationChecker([]).check(doc)
    missing = [f for f in findings if "not found" in f.message]
    assert len(missing) == 1
    assert missing[0].severity == Severity.error
    assert missing[0].line == 1


def test_cited_key_present_in_bib_is_silent():
    doc = _doc("Hello \\cite{smith2020} world\n")
    findings = CitationChecker([_entry("smith2020")]).check(doc)
    assert [f for f in findings if "not found" in f.message] == []


def test_unused_entry_is_info():
    doc = _doc("Hello world\n")
    findings = CitationChecker([_entry("orphan")]).check(doc)
    assert len(findings) == 1
    assert findings[0].severity == Severity.info
    assert "Unused" in findings[0].message
    assert findings[0].file == "refs.bib"


def test_duplicate_entries_produce_warnings_for_each_after_first():
    doc = _doc("\\cite{k}\n")
    entries = [_entry("k", line=10), _entry("k", line=20), _entry("k", line=30)]
    findings = CitationChecker(entries).check(doc)
    dups = [f for f in findings if "Duplicate" in f.message]
    assert [(f.line, f.severity) for f in dups] == [
        (20, Severity.warning),
        (30, Severity.warning),
    ]
