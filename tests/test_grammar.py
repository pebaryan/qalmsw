from pathlib import Path

from qalmsw.checkers import GrammarChecker, Severity
from qalmsw.document import Document
from qalmsw.parse import Paragraph


def _doc(paragraphs: list[Paragraph]) -> Document:
    return Document(path=Path("test.tex"), source="", paragraphs=paragraphs)


class FakeLLM:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return self.response


def test_finding_shape_and_line_mapping():
    para = Paragraph(
        text="This is a sentance with a typo.\nSecond line here.",
        start_line=10,
        end_line=11,
    )
    llm = FakeLLM(
        {
            "issues": [
                {
                    "excerpt": "sentance",
                    "message": "misspelled",
                    "suggestion": "sentence",
                    "severity": "warning",
                }
            ]
        }
    )
    findings = GrammarChecker(llm).check(_doc([para]))
    assert len(findings) == 1
    f = findings[0]
    assert f.checker == "grammar"
    assert f.line == 10
    assert f.severity == Severity.warning
    assert f.suggestion == "sentence"
    assert f.excerpt == "sentance"


def test_excerpt_on_later_line_maps_correctly():
    para = Paragraph(
        text="First line.\nSecond line has issue here.",
        start_line=5,
        end_line=6,
    )
    llm = FakeLLM({"issues": [{"excerpt": "issue here", "message": "x", "severity": "info"}]})
    findings = GrammarChecker(llm).check(_doc([para]))
    assert findings[0].line == 6


def test_empty_response_yields_no_findings():
    para = Paragraph(
        text="The text here reads reasonably well and needs no changes.",
        start_line=1,
        end_line=1,
    )
    assert GrammarChecker(FakeLLM({"issues": []})).check(_doc([para])) == []


def test_unknown_severity_defaults_to_warning():
    para = Paragraph(
        text="The first line contains some reasonably long prose content.",
        start_line=1,
        end_line=1,
    )
    llm = FakeLLM({"issues": [{"excerpt": "prose", "message": "m", "severity": "BOGUS"}]})
    findings = GrammarChecker(llm).check(_doc([para]))
    assert findings[0].severity == Severity.warning


def test_missing_excerpt_falls_back_to_paragraph_start():
    para = Paragraph(
        text="This paragraph contains enough words to qualify as prose.",
        start_line=7,
        end_line=7,
    )
    llm = FakeLLM({"issues": [{"message": "vague", "severity": "info"}]})
    findings = GrammarChecker(llm).check(_doc([para]))
    assert findings[0].line == 7


def test_prose_less_paragraphs_skip_llm_call():
    para = Paragraph(text="\\maketitle", start_line=3, end_line=3)
    llm = FakeLLM({"issues": [{"excerpt": "x", "message": "m"}]})
    assert GrammarChecker(llm).check(_doc([para])) == []
    assert llm.calls == []
