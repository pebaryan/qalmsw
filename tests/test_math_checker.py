from pathlib import Path

from qalmsw.checkers import MathChecker, Severity
from qalmsw.document import Document
from qalmsw.parse import Paragraph


class FakeLLM:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return self.response


def _doc(paragraphs: list[Paragraph]) -> Document:
    return Document(path=Path("test.tex"), source="", paragraphs=paragraphs)


def test_math_paragraph_triggers_checker():
    para = Paragraph(
        text="We define $x$ and later write $x_i$ for the same quantity.",
        start_line=12,
        end_line=12,
    )
    llm = FakeLLM(
        {
            "issues": [
                {
                    "excerpt": "x_i",
                    "message": "indexing changes without explanation",
                    "suggestion": "define the subscript or keep the notation consistent",
                    "severity": "warning",
                }
            ]
        }
    )
    findings = MathChecker(llm).check(_doc([para]))
    assert len(findings) == 1
    f = findings[0]
    assert f.checker == "math"
    assert f.line == 12
    assert f.severity == Severity.warning
    assert f.suggestion == "define the subscript or keep the notation consistent"
    assert f.excerpt == "x_i"


def test_later_line_excerpt_maps_correctly():
    para = Paragraph(
        text="First line of math.\nSecond line has $y$ and inconsistency here.",
        start_line=3,
        end_line=4,
    )
    llm = FakeLLM(
        {"issues": [{"excerpt": "inconsistency here", "message": "x", "severity": "info"}]}
    )
    findings = MathChecker(llm).check(_doc([para]))
    assert findings[0].line == 4


def test_non_math_paragraph_skips_llm_call():
    para = Paragraph(text="This paragraph has no formulas at all.", start_line=1, end_line=1)
    llm = FakeLLM({"issues": [{"excerpt": "x", "message": "m"}]})
    assert MathChecker(llm).check(_doc([para])) == []
    assert llm.calls == []


def test_unknown_severity_defaults_to_warning():
    para = Paragraph(text="We write $x=1$ in the model.", start_line=1, end_line=1)
    llm = FakeLLM({"issues": [{"excerpt": "x=1", "message": "m", "severity": "BOGUS"}]})
    findings = MathChecker(llm).check(_doc([para]))
    assert findings[0].severity == Severity.warning
