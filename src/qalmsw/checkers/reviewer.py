"""Reviewer-style critique.

One LLM call per `\\section{}` (or the whole body if no sections). The prompt asks for
substantive concerns — motivation, clarity, argumentation, methodology, evaluation —
and explicitly discourages grammar nit-picking (GrammarChecker handles that).

Over-long sections are truncated to `max_chars` so we don't blow past local-model
context. The default (12000 chars ≈ 3000 tokens) is safe for 8k-context models once
the prompt and response budget are accounted for. Raise it if your server allows more.
"""
from __future__ import annotations

from qalmsw._concurrency import ordered_parallel_map
from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document
from qalmsw.llm import LLMClient
from qalmsw.parse import Section, parse_sections

_SYSTEM_PROMPT = """You are reviewing a section of a scientific paper.

Identify substantive concerns about motivation, clarity, argumentation, methodology, \
evaluation, or structure. Be concise, specific, and actionable. Do NOT comment on \
grammar, spelling, or LaTeX formatting — those are checked separately. If the section \
reads well, return zero comments.

Respond with a JSON object of this exact form:
{
  "comments": [
    {
      "category": "motivation|clarity|argumentation|methodology|evaluation|structure",
      "severity": "info|warning|error",
      "message": "the concern, one or two sentences",
      "suggestion": "optional concrete improvement"
    }
  ]
}

If there are no substantive issues, return {"comments": []}.
"""

_DEFAULT_MAX_CHARS = 12000
_TRUNCATION_NOTE = "\n\n[... section truncated for length ...]"


class ReviewerChecker:
    name = "reviewer"

    def __init__(
        self,
        llm: LLMClient,
        max_chars: int = _DEFAULT_MAX_CHARS,
        concurrency: int = 1,
    ) -> None:
        self._llm = llm
        self._max_chars = max_chars
        self._concurrency = concurrency

    def check(self, doc: Document) -> list[Finding]:
        sections = [
            s
            for s in parse_sections(doc.source, line_map=doc.line_map, default_file=doc.path)
            if s.text.strip()
        ]
        results = ordered_parallel_map(
            lambda s: self._llm.complete_json(_SYSTEM_PROMPT, self._render_user_prompt(s)),
            sections,
            self._concurrency,
        )
        findings: list[Finding] = []
        for section, result in zip(sections, results, strict=True):
            for raw in result.get("comments", []):
                findings.append(_to_finding(raw, section, self.name))
        return findings

    def _render_user_prompt(self, section: Section) -> str:
        text = section.text
        if len(text) > self._max_chars:
            text = text[: self._max_chars] + _TRUNCATION_NOTE
        if section.title:
            return f"Section title: {section.title}\n\n{text}"
        return text


def _to_finding(raw: dict, section: Section, checker: str) -> Finding:
    category = (raw.get("category") or "").strip()
    body = (raw.get("message") or "").strip()
    prefix = f"[{category}] " if category else ""
    severity_str = raw.get("severity", "info")
    try:
        severity = Severity(severity_str)
    except ValueError:
        severity = Severity.info
    return Finding(
        checker=checker,
        severity=severity,
        line=section.start_line,
        message=prefix + body,
        suggestion=(raw.get("suggestion") or None),
        file=str(section.file) if section.file else None,
    )
