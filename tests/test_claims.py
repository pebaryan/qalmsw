from pathlib import Path

from qalmsw.bib import BibEntry
from qalmsw.checkers import ClaimsChecker, Severity
from qalmsw.document import Document
from qalmsw.parse import Paragraph
from qalmsw.retrieval import ScholarResult


class ScriptedLLM:
    """Returns responses in order. System prompt is used to pick the right script."""

    def __init__(self, extract: list[dict] | None = None, judge: list[dict] | None = None) -> None:
        self._extract = list(extract or [])
        self._judge = list(judge or [])
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        if "extracting citation-backed claims" in system:
            return self._extract.pop(0) if self._extract else {"claims": []}
        if "checking whether an abstract supports" in system:
            return self._judge.pop(0) if self._judge else {"verdict": "unclear", "rationale": ""}
        raise AssertionError(f"unexpected system prompt: {system[:60]}")


def _doc(paragraphs: list[Paragraph]) -> Document:
    return Document(path=Path("test.tex"), source="", paragraphs=paragraphs)


def _entry(key: str, title: str = "A Paper") -> BibEntry:
    return BibEntry(key=key, entry_type="article", file=Path("t.bib"), line=1, title=title)


def _stub_search(title: str, abstract: str = "Some abstract text.") -> callable:
    def fn(_: str) -> ScholarResult | None:
        return ScholarResult(title=title, authors=[], year=None, abstract=abstract, url=None)
    return fn


def test_supports_verdict_produces_no_finding():
    para = Paragraph(text="LLMs are powerful \\cite{foo}.", start_line=10, end_line=10)
    llm = ScriptedLLM(
        extract=[{"claims": [{"claim": "LLMs are powerful", "cite_keys": ["foo"]}]}],
        judge=[{"verdict": "supports", "rationale": "abstract confirms"}],
    )
    findings = ClaimsChecker(llm, [_entry("foo", "Big LLMs")], search=_stub_search("Big LLMs")).check(
        _doc([para])
    )
    assert findings == []


def test_contradicts_verdict_produces_error_finding():
    para = Paragraph(text="X always works \\cite{foo}.", start_line=5, end_line=5)
    llm = ScriptedLLM(
        extract=[{"claims": [{"claim": "X always works", "cite_keys": ["foo"]}]}],
        judge=[{"verdict": "contradicts", "rationale": "abstract says otherwise"}],
    )
    findings = ClaimsChecker(llm, [_entry("foo")], search=_stub_search("A Paper")).check(_doc([para]))
    assert len(findings) == 1
    f = findings[0]
    assert f.checker == "claims"
    assert f.severity == Severity.error
    assert f.line == 5
    assert "contradicts" in f.message
    assert "abstract says otherwise" in f.message


def test_unrelated_and_unclear_are_warnings():
    para = Paragraph(text="Claim text \\cite{foo} \\cite{bar}.", start_line=1, end_line=1)
    llm = ScriptedLLM(
        extract=[{"claims": [{"claim": "Claim text", "cite_keys": ["foo", "bar"]}]}],
        judge=[
            {"verdict": "unrelated", "rationale": "different topic"},
            {"verdict": "unclear", "rationale": "abstract silent"},
        ],
    )
    findings = ClaimsChecker(
        llm, [_entry("foo"), _entry("bar")], search=_stub_search("A Paper")
    ).check(_doc([para]))
    assert [f.severity for f in findings] == [Severity.warning, Severity.warning]


def test_paragraph_without_cite_skips_extraction():
    para = Paragraph(text="Plain prose no citations here.", start_line=1, end_line=1)
    llm = ScriptedLLM()
    ClaimsChecker(llm, [], search=_stub_search("x")).check(_doc([para]))
    assert llm.calls == []


def test_unknown_cite_key_yields_info_finding():
    para = Paragraph(text="A claim \\cite{missing}.", start_line=1, end_line=1)
    llm = ScriptedLLM(extract=[{"claims": [{"claim": "A claim", "cite_keys": ["missing"]}]}])
    findings = ClaimsChecker(llm, [], search=_stub_search("x")).check(_doc([para]))
    assert len(findings) == 1
    assert findings[0].severity == Severity.info
    assert "Unknown cite key 'missing'" in findings[0].message


def test_missing_title_yields_info_finding():
    para = Paragraph(text="A claim \\cite{foo}.", start_line=1, end_line=1)
    llm = ScriptedLLM(extract=[{"claims": [{"claim": "A claim", "cite_keys": ["foo"]}]}])
    findings = ClaimsChecker(
        llm, [_entry("foo", title="")], search=_stub_search("x")
    ).check(_doc([para]))
    assert findings[0].severity == Severity.info
    assert "No title in bib" in findings[0].message


def test_scholar_miss_yields_info_finding():
    para = Paragraph(text="A claim \\cite{foo}.", start_line=1, end_line=1)
    llm = ScriptedLLM(extract=[{"claims": [{"claim": "A claim", "cite_keys": ["foo"]}]}])

    def empty(_: str) -> ScholarResult | None:
        return None

    findings = ClaimsChecker(llm, [_entry("foo")], search=empty).check(_doc([para]))
    assert findings[0].severity == Severity.info
    assert "Could not retrieve abstract" in findings[0].message


def test_scholar_exception_is_caught():
    para = Paragraph(text="A claim \\cite{foo}.", start_line=1, end_line=1)
    llm = ScriptedLLM(extract=[{"claims": [{"claim": "A claim", "cite_keys": ["foo"]}]}])

    def boom(_: str) -> ScholarResult | None:
        raise RuntimeError("network failed")

    findings = ClaimsChecker(llm, [_entry("foo")], search=boom).check(_doc([para]))
    assert findings[0].severity == Severity.info
    assert "Could not retrieve abstract" in findings[0].message


def test_abstract_is_cached_per_bib_key():
    para1 = Paragraph(text="Claim one \\cite{foo}.", start_line=1, end_line=1)
    para2 = Paragraph(text="Claim two \\cite{foo}.", start_line=2, end_line=2)
    llm = ScriptedLLM(
        extract=[
            {"claims": [{"claim": "Claim one", "cite_keys": ["foo"]}]},
            {"claims": [{"claim": "Claim two", "cite_keys": ["foo"]}]},
        ],
        judge=[
            {"verdict": "supports", "rationale": "ok"},
            {"verdict": "supports", "rationale": "ok"},
        ],
    )
    call_count = {"n": 0}

    def counting_search(_: str) -> ScholarResult | None:
        call_count["n"] += 1
        return ScholarResult(title="x", authors=[], year=None, abstract="abs", url=None)

    ClaimsChecker(llm, [_entry("foo")], search=counting_search).check(_doc([para1, para2]))
    assert call_count["n"] == 1
