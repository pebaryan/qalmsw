"""Per-paragraph grammar / style checker.

Asks the LLM for issues in each paragraph, then maps each issue's excerpt back to an
absolute source line by searching for the excerpt inside the paragraph text. Asking the
LLM to count lines itself is unreliable for small local models, so we don't.
"""
from __future__ import annotations

from qalmsw.checkers.base import Finding, Severity
from qalmsw.llm import LLMClient
from qalmsw.parse import Paragraph

_SYSTEM_PROMPT = """You are a grammar and style checker for scientific LaTeX writing.

Review the paragraph and identify concrete grammar, spelling, punctuation, or obvious \
style issues. Ignore LaTeX commands (\\cite, \\ref, \\section, math environments, etc.) \
— treat them as opaque tokens. Do NOT comment on content, structure, or citations. Keep \
suggestions minimal and specific.

Respond with a JSON object of this exact form:
{
  "issues": [
    {
      "excerpt": "exact substring from the paragraph containing the issue",
      "message": "short description of the issue",
      "suggestion": "proposed replacement text",
      "severity": "info" | "warning" | "error"
    }
  ]
}

If there are no issues, return {"issues": []}.
"""


class GrammarChecker:
    name = "grammar"

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def check(self, paragraphs: list[Paragraph]) -> list[Finding]:
        findings: list[Finding] = []
        for para in paragraphs:
            result = self._llm.complete_json(_SYSTEM_PROMPT, para.text)
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
        message=raw.get("message", "").strip(),
        suggestion=(raw.get("suggestion") or None),
        excerpt=excerpt or None,
    )


def _locate_line(para: Paragraph, excerpt: str) -> int:
    if not excerpt:
        return para.start_line
    idx = para.text.find(excerpt)
    if idx < 0:
        return para.start_line
    return para.start_line + para.text[:idx].count("\n")
