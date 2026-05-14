"""LLM Artifact Checker — catches telltale signs of uncurated LLM-generated content.

Scans the full document source (not just prose paragraphs) for regex patterns that
indicate the authors pasted LLM output without review. These are the "incontrovertible
evidence" patterns that arXiv's Code of Conduct penalises with a 1-year ban.

Categories:
- **meta_comments**: LLM conversational fluff ("here is a X-word summary",
  "would you like me to", "I'd be happy to")
- **placeholder_data**: Template filler that was never replaced ("fill in with
  the real numbers", "illustrative data", "insert figure here")
- **self_awareness**: LLM self-references ("as an AI language model",
  "I don't have access to", "I cannot provide")
- **phantom_references**: Placeholder labels/captions ("Figure X. Insert caption",
  "Table placeholder", "Add caption")
- **latex_artifacts**: LLM-added LaTeX boilerplate that doesn't belong in a
  real paper ("\\todo{Your text here}", "\\lipsum", unexpected "\\begin{abstract}"
  duplicates)
"""

from __future__ import annotations

import re

from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document

# ---------------------------------------------------------------------------
# Pattern definitions
# Each entry: (compiled_regex, severity, category_label, message_template)
# Ordered by severity (error patterns first), then by specificity.
# ---------------------------------------------------------------------------

_EGREGIOUS_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # Meta-comments: LLM telling the author what it did
    (
        re.compile(
            r"here\s+is\s+(?:a|an)\s+"
            r"(?:\d{1,4}[-\s]?(?:word|paragraph|sentence|page)\s+)?"
            r"(?:summary|overview|outline|description|explanation|analysis)",
            re.IGNORECASE,
        ),
        "meta_comments",
        "LLM meta-comment: 'here is a ... summary' — uncurated AI output",
    ),
    (
        re.compile(
            r"would\s+you\s+like\s+me\s+to\s+(?:make\s+(?:any\s+)?changes|"
            r"(?:expand|elaborate|clarify|rewrite|continue|add|modify|adjust))",
            re.IGNORECASE,
        ),
        "meta_comments",
        "LLM meta-comment: 'would you like me to ...' — AI conversational artifact",
    ),
    (
        re.compile(
            r"I[',]?d\s+be\s+happy\s+to",
            re.IGNORECASE,
        ),
        "meta_comments",
        "LLM meta-comment: 'I'd be happy to' — AI assistant phrasing",
    ),
    (
        re.compile(
            r"I[',]?d\s+be\s+glad\s+to",
            re.IGNORECASE,
        ),
        "meta_comments",
        "LLM meta-comment: 'I'd be glad to' — AI assistant phrasing",
    ),
    # Placeholder data
    (
        re.compile(
            r"(?:fill|replace|populate|substitute)"
            r"(?:\s+(?:it|them|this))?"
            r"\s+in"
            r"(?:\s+with)?"
            r"(?:\s+the)?"
            r"\s+(?:real|actual|proper|correct|your)\s+"
            r"(?:data|numbers|values|results|content|information)",
            re.IGNORECASE,
        ),
        "placeholder_data",
        "LLM placeholder: 'fill in with the real data' — unedited template content",
    ),
    (
        re.compile(
            r"(?:this|the|these)\s+(?:data|table|figure|numbers|results|values)"
            r"\s+(?:is|are)\s+illustrative",
            re.IGNORECASE,
        ),
        "placeholder_data",
        "LLM placeholder: 'data is illustrative' — unedited template content",
    ),
    (
        re.compile(
            r"(?:this|the)\s+(?:is\s+)?(?:a\s+)?(?:sample|draft|template|example)"
            r"\s+(?:table|figure|section|paragraph|content)",
            re.IGNORECASE,
        ),
        "placeholder_data",
        "LLM placeholder: 'sample table / draft section' — unedited template",
    ),
    (
        re.compile(
            r"(?:insert|add|put)\s+(?:your\s+)?(?:content|text|data|information|"
            r"details|description|results)\s+here",
            re.IGNORECASE,
        ),
        "placeholder_data",
        "LLM placeholder: 'insert your content here' — unedited template",
    ),
    (
        re.compile(
            r"(?:\[|\\\[)\s*(?:insert|add|put)\s+(?:figure|image|table|chart|graph|"
            r"diagram|illustration|screenshot)\s*(?:here|above|below)?\s*(?:\]|\\\])",
            re.IGNORECASE,
        ),
        "placeholder_data",
        "LLM placeholder: '[insert figure]' — phantom reference",
    ),
    # Self-awareness / refusal artifacts
    (
        re.compile(
            r"as\s+an\s+AI\s+(?:language\s+)?(?:model|assistant)",
            re.IGNORECASE,
        ),
        "self_awareness",
        "LLM self-reference: 'as an AI language model' — uncurated AI output",
    ),
    (
        re.compile(
            r"I\s+(?:do\s+)?n[o']t\s+(?:have\s+access\s+to\s+"
            r"(?:the\s+)?(?:internet|real[-\s]?time\s+(?:data|information)|"
            r"specific\s+(?:data|information))"
            r"|can(?:not)?\s+(?:access|retrieve|browse|look\s+up))",
            re.IGNORECASE,
        ),
        "self_awareness",
        "LLM self-reference: 'I don't have access to...' — AI limitation statement",
    ),
    (
        re.compile(
            r"I\s+(?:ca|ca)n['']?t\s+(?:provide|generate|create|write|help\s+with)",
            re.IGNORECASE,
        ),
        "self_awareness",
        "LLM refusal: 'I cannot provide/generate...' — uncurated AI output",
    ),
    (
        re.compile(
            r"I['']?m\s+(?:sorry|afraid|unable)\s*,\s*(?:but\s+)?(?:I|i)",
            re.IGNORECASE,
        ),
        "self_awareness",
        "LLM refusal: 'I'm sorry, but I...' — AI apology pattern",
    ),
    # Phantom labels
    (
        re.compile(
            r"\\caption\s*\{[^}]*"
            r"(?:placeholder|draft|template|add\s+caption|"
            r"caption\s+(?:text|here|goes\s+here)|"
            r"your\s+caption\s+(?:here|text)|"
            r"insert\s+caption|"
            r"todo\s*:?\s*add\s+caption)"
            r"[^}]*\}",
            re.IGNORECASE | re.DOTALL,
        ),
        "phantom_references",
        "Phantom caption: placeholder text in \\caption{} — unedited template",
    ),
    (
        re.compile(
            r"\\label\s*\{[^}]*"
            r"(?:placeholder|draft|todo|fixme|xxx|replace)"
            r"[^}]*\}",
            re.IGNORECASE,
        ),
        "phantom_references",
        "Phantom label: placeholder label name — unedited template",
    ),
]

_WARNING_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # LaTeX boilerplate that shouldn't survive in a finished manuscript
    (
        re.compile(r"\\lipsum(?:\s*\[[^\]]*\])?", re.IGNORECASE),
        "latex_artifacts",
        "LaTeX artifact: \\lipsum — filler text left in document",
    ),
    (
        re.compile(r"\\blindtext(?:\s*\[\d+\])?", re.IGNORECASE),
        "latex_artifacts",
        "LaTeX artifact: \\blindtext — filler text left in document",
    ),
    # TODO markers in text (not in LaTeX comments, detected via the body source)
    (
        re.compile(r"\bTODO\b\s*:?\s*(?:add|insert|write|fill|complete|update)",
                    re.IGNORECASE),
        "placeholder_data",
        "TODO artifact: unfulfilled TODO marker in document body",
    ),
    (
        re.compile(r"\bFIXME\b", re.IGNORECASE),
        "placeholder_data",
        "FIXME marker: unresolved fixme in document body",
    ),
    # Data table with obviously made-up numbers
    (
        re.compile(
            r"\\begin\s*\{tabular\}\s*\{[^}]*\}\s*\n?"
            r"\s*[A-Za-z].*?&.*?\d+\s*\\\\\s*\n?"
            r"\s*[A-Za-z].*?&.*?\d+\s*\\\\\s*\n?"
            r"\s*(?:[A-Za-z].*?&.*?\d+|\\\\\s*(?:bottomrule|hline|hline))",
            re.DOTALL,
        ),
        "latex_artifacts",
        "Table with minimal rows — possible illustrative/placeholder table",
    ),
]


class ArtifactChecker:
    """Scans the full document source for LLM-generated artifact patterns.

    Deterministic (no LLM calls), runs on every check regardless of --skip flags.
    """

    name = "artifacts"

    def check(self, doc: Document) -> list[Finding]:
        findings: list[Finding] = []

        # Scan body text (after \begin{document}, before \end{document})
        body, body_offset = _extract_body_segment(doc.source)

        findings.extend(self._scan_patterns(body, body_offset, _EGREGIOUS_PATTERNS, Severity.error))
        findings.extend(self._scan_patterns(body, body_offset, _WARNING_PATTERNS, Severity.warning))

        # Also scan the preamble for phantom references
        preamble, _ = _extract_preamble(doc.source)
        findings.extend(
            self._scan_patterns(preamble, 1, _EGREGIOUS_PATTERNS, Severity.error)
        )
        findings.extend(
            self._scan_patterns(preamble, 1, _WARNING_PATTERNS, Severity.warning)
        )

        return findings

    @staticmethod
    def _scan_patterns(
        text: str,
        line_offset: int,
        patterns: list[tuple[re.Pattern[str], str, str]],
        severity: Severity,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for regex, _category, message in patterns:
            for match in regex.finditer(text):
                line = text[: match.start()].count("\n") + line_offset
                excerpt = match.group(0)[:80].strip()
                findings.append(
                    Finding(
                        checker="artifacts",
                        severity=severity,
                        line=line,
                        message=message,
                        excerpt=excerpt,
                        suggestion=(
                            "Review and replace with your own content, or "
                            "remove this text entirely before submission."
                        ),
                    )
                )
        return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BEGIN_DOC_RE = re.compile(r"\\begin\{document\}")
_END_DOC_RE = re.compile(r"\\begin\{thebibliography\}|\\end\{document\}")


def _extract_body_segment(source: str) -> tuple[str, int]:
    """Return (body_text, body_start_line_1indexed)."""
    begin = _BEGIN_DOC_RE.search(source)
    if not begin:
        return source, 1
    offset = begin.end()
    if offset < len(source) and source[offset] == "\n":
        offset += 1
    end = _END_DOC_RE.search(source, offset)
    end_offset = end.start() if end else len(source)
    start_line = source.count("\n", 0, offset) + 1
    return source[offset:end_offset], start_line


def _extract_preamble(source: str) -> tuple[str, int]:
    """Return the preamble (everything before \\begin{document})."""
    begin = _BEGIN_DOC_RE.search(source)
    if not begin:
        return "", 1
    return source[: begin.start()], 1
