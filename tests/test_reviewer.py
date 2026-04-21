from pathlib import Path

from qalmsw.checkers import ReviewerChecker, Severity
from qalmsw.document import Document


class FakeLLM:
    def __init__(self, responses: list[dict] | dict) -> None:
        self._responses = responses if isinstance(responses, list) else [responses]
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def _doc(source: str) -> Document:
    return Document(path=Path("test.tex"), source=source, paragraphs=[])


def test_finding_line_matches_section_start():
    source = (
        "\\begin{document}\n"
        "\\section{Intro}\n"
        "body\n"
        "\\end{document}\n"
    )
    llm = FakeLLM(
        {
            "comments": [
                {
                    "category": "clarity",
                    "severity": "warning",
                    "message": "thesis is unclear",
                    "suggestion": "state the claim up front",
                }
            ]
        }
    )
    findings = ReviewerChecker(llm).check(_doc(source))
    assert len(findings) == 1
    f = findings[0]
    assert f.checker == "reviewer"
    assert f.line == 2
    assert f.severity == Severity.warning
    assert f.message.startswith("[clarity] ")
    assert "thesis is unclear" in f.message
    assert f.suggestion == "state the claim up front"


def test_one_llm_call_per_section():
    source = (
        "\\begin{document}\n"
        "\\section{A}\n"
        "first\n"
        "\\section{B}\n"
        "second\n"
        "\\end{document}\n"
    )
    llm = FakeLLM({"comments": []})
    ReviewerChecker(llm).check(_doc(source))
    assert len(llm.calls) == 2


def test_unknown_severity_defaults_to_info():
    source = "\\begin{document}\n\\section{X}\nbody\n\\end{document}\n"
    llm = FakeLLM({"comments": [{"severity": "BOGUS", "message": "m"}]})
    findings = ReviewerChecker(llm).check(_doc(source))
    assert findings[0].severity == Severity.info


def test_empty_comments_yields_no_findings():
    source = "\\begin{document}\n\\section{X}\nbody\n\\end{document}\n"
    assert ReviewerChecker(FakeLLM({"comments": []})).check(_doc(source)) == []


def test_empty_section_skips_llm_call():
    source = "\\begin{document}\n\\end{document}\n"
    llm = FakeLLM({"comments": [{"message": "should not appear"}]})
    assert ReviewerChecker(llm).check(_doc(source)) == []
    assert llm.calls == []


def test_long_section_is_truncated_in_prompt():
    body = "x " * 10000
    source = f"\\begin{{document}}\n\\section{{Long}}\n{body}\n\\end{{document}}\n"
    llm = FakeLLM({"comments": []})
    ReviewerChecker(llm, max_chars=500).check(_doc(source))
    _, user = llm.calls[0]
    assert "[... section truncated for length ...]" in user
    assert len(user) < 1000


def test_missing_category_omits_prefix():
    source = "\\begin{document}\n\\section{X}\nbody\n\\end{document}\n"
    llm = FakeLLM({"comments": [{"message": "bare message", "severity": "info"}]})
    findings = ReviewerChecker(llm).check(_doc(source))
    assert findings[0].message == "bare message"
