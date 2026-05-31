"""Math formula consistency checker.

Runs one LLM pass per paragraph that appears to contain LaTeX math. The prompt asks
for concrete notation or consistency issues, such as conflicting symbol definitions,
inconsistent indexing, mismatched variable names, or equation/text disagreement.

Like the grammar checker, the model returns excerpts rather than line numbers; we map
the excerpt back to the source line locally so findings stay anchored to the right
file.
"""
from __future__ import annotations

from qalmsw._concurrency import ordered_parallel_map
from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document
from qalmsw.llm import LLMClient
from qalmsw.parse import Paragraph, has_math

_SYSTEM_PROMPT = """You are a math formula consistency checker for scientific LaTeX.

Review the paragraph and identify concrete issues with formulas, notation, or math-text
consistency. Focus on problems such as:
- the same symbol being used for different quantities,
- a variable or index changing without explanation,
- inconsistent notation between prose and formulas,
- equations that appear to disagree with nearby text,
- missing or mismatched symbols that make the formula hard to interpret.

Do NOT do algebraic proof checking or general scientific fact checking. Only report
issues that are concrete and local to the provided paragraph.

Respond with a JSON object of this exact form:
{
  "issues": [
    {
      "excerpt": "exact substring from the paragraph containing the issue",
      "message": "short description of the inconsistency",
      "suggestion": "proposed correction or clarification",
      "severity": "info" | "warning" | "error"
    }
  ]
}

If there are no issues, return {"issues": []}.
"""


class MathChecker:
    name = "math"

    def __init__(self, llm: LLMClient, concurrency: int = 1) -> None:
        self._llm = llm
        self._concurrency = concurrency

    def check(self, doc: Document) -> list[Finding]:
        math_paras = [p for p in doc.paragraphs if has_math(p.text)]
        results = ordered_parallel_map(
            lambda p: self._llm.complete_json(_SYSTEM_PROMPT, p.text),
            math_paras,
            self._concurrency,
        )
        findings: list[Finding] = []
        for para, result in zip(math_paras, results, strict=True):
            for raw in result.get("issues", []):
                findings.append(_to_finding(raw, para, self.name))
        return findings


def _to_finding(raw: dict, para: Paragraph, checker: str) -> Finding:
    excerpt = (raw.get("excerpt") or "").strip()
    severity_str = raw.get("severity", "warning")
    try:
        severity = Severity(severity_str)
    except ValueError:
        severity = Severity.warning
    return Finding(
        checker=checker,
        severity=severity,
        line=_locate_line(para, excerpt),
        message=(raw.get("message") or "").strip(),
        suggestion=(raw.get("suggestion") or None),
        excerpt=excerpt or None,
        file=str(para.file) if para.file else None,
    )


def _locate_line(para: Paragraph, excerpt: str) -> int:
    if not excerpt:
        return para.start_line
    idx = para.text.find(excerpt)
    if idx < 0:
        return para.start_line
    return para.start_line + para.text[:idx].count("\n")
