"""Minimal .tex parser: body extraction + paragraph splitting with source line tracking.

The contract other modules rely on: `parse_paragraphs` returns `Paragraph` objects whose
`start_line`/`end_line` are 1-indexed against the *original* file, so Findings can point
back at the real source location.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_BEGIN_DOC_RE = re.compile(r"\\begin\{document\}")
_END_DOC_RE = re.compile(r"\\end\{document\}")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?")
_WORD_RE = re.compile(r"[A-Za-z]{3,}")


@dataclass(frozen=True)
class Paragraph:
    text: str
    start_line: int
    end_line: int


def _strip_comments(source: str) -> str:
    # Replace comment runs with empty string but keep the newline so line numbers are stable.
    return _COMMENT_RE.sub("", source)


def extract_body(source: str) -> tuple[str, int]:
    """Return (body_text, body_start_line_1indexed).

    If `\\begin{document}` is absent, the whole source is treated as the body.
    """
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


def parse_paragraphs(source: str) -> list[Paragraph]:
    """Split the document body into blank-line-separated paragraphs."""
    body, body_start_line = extract_body(source)
    stripped = _strip_comments(body)
    lines = stripped.splitlines()

    paragraphs: list[Paragraph] = []
    buf: list[str] = []
    buf_start: int | None = None

    def flush(end_line: int) -> None:
        if not buf:
            return
        text = "\n".join(buf).strip()
        if text:
            paragraphs.append(Paragraph(text=text, start_line=buf_start, end_line=end_line))
        buf.clear()

    for i, line in enumerate(lines):
        line_number = body_start_line + i
        if line.strip() == "":
            flush(end_line=line_number - 1)
            buf_start = None
        else:
            if buf_start is None:
                buf_start = line_number
            buf.append(line)

    if buf:
        flush(end_line=body_start_line + len(lines) - 1)

    return paragraphs


def has_prose(text: str, min_words: int = 3) -> bool:
    """True if `text` contains at least `min_words` word-like tokens after stripping
    simple LaTeX commands. Used to skip paragraphs that are entirely structural
    (`\\maketitle`, `\\section{X}`, etc.) and not worth an LLM call.
    """
    cleaned = _LATEX_CMD_RE.sub(" ", text)
    return len(_WORD_RE.findall(cleaned)) >= min_words
