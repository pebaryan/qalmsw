from qalmsw.checkers import GrammarChecker, Severity
from qalmsw.parse import Paragraph


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
    findings = GrammarChecker(llm).check([para])
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
    findings = GrammarChecker(llm).check([para])
    assert findings[0].line == 6


def test_empty_response_yields_no_findings():
    para = Paragraph(text="Clean.", start_line=1, end_line=1)
    assert GrammarChecker(FakeLLM({"issues": []})).check([para]) == []


def test_unknown_severity_defaults_to_warning():
    para = Paragraph(text="x", start_line=1, end_line=1)
    llm = FakeLLM({"issues": [{"excerpt": "x", "message": "m", "severity": "BOGUS"}]})
    findings = GrammarChecker(llm).check([para])
    assert findings[0].severity == Severity.warning


def test_missing_excerpt_falls_back_to_paragraph_start():
    para = Paragraph(text="content", start_line=7, end_line=7)
    llm = FakeLLM({"issues": [{"message": "vague", "severity": "info"}]})
    findings = GrammarChecker(llm).check([para])
    assert findings[0].line == 7
