import time
from pathlib import Path

from qalmsw._concurrency import ordered_parallel_map
from qalmsw.checkers import GrammarChecker, ReviewerChecker
from qalmsw.document import Document
from qalmsw.parse import Paragraph


def test_ordered_parallel_map_preserves_order_with_jitter():
    def slow(x: int) -> int:
        time.sleep(0.02 if x % 2 == 0 else 0.0)
        return x * 10

    result = ordered_parallel_map(slow, [1, 2, 3, 4, 5], concurrency=4)
    assert result == [10, 20, 30, 40, 50]


def test_ordered_parallel_map_serial_path_for_concurrency_one():
    result = ordered_parallel_map(lambda x: x + 1, [1, 2, 3], concurrency=1)
    assert result == [2, 3, 4]


def test_ordered_parallel_map_empty_input():
    assert ordered_parallel_map(lambda x: x, [], concurrency=4) == []


class _ConcurrentLLM:
    """FakeLLM that returns a per-paragraph-indexed response so we can verify
    that a parallel checker still maps each result back to the right paragraph."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append(user)
        # A short sleep magnifies the probability that out-of-order completion
        # would corrupt the result-to-paragraph mapping if the checker had a bug.
        time.sleep(0.01)
        token = user.strip().split()[-1]
        return {
            "issues": [{"excerpt": token, "message": f"flag-{token}", "severity": "info"}],
            "comments": [{"message": f"comment-{token}", "severity": "info"}],
        }


def _doc(paragraphs: list[Paragraph], source: str = "") -> Document:
    return Document(path=Path("test.tex"), source=source, paragraphs=paragraphs)


def test_grammar_parallel_run_preserves_paragraph_association():
    paras = [
        Paragraph(text=f"The paragraph number is alpha{i}", start_line=i + 1, end_line=i + 1)
        for i in range(6)
    ]
    findings = GrammarChecker(_ConcurrentLLM(), concurrency=4).check(_doc(paras))
    assert [f.message for f in findings] == [f"flag-alpha{i}" for i in range(6)]
    assert [f.line for f in findings] == [i + 1 for i in range(6)]


def test_reviewer_parallel_run_preserves_section_association():
    source = (
        "\\begin{document}\n"
        "\\section{One}\ntoken-one\n"
        "\\section{Two}\ntoken-two\n"
        "\\section{Three}\ntoken-three\n"
        "\\end{document}\n"
    )
    findings = ReviewerChecker(_ConcurrentLLM(), concurrency=4).check(_doc([], source))
    messages = [f.message for f in findings]
    assert messages == ["comment-token-one", "comment-token-two", "comment-token-three"]
