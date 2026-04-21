"""Minimal .tex parser: body extraction + paragraph splitting with source line tracking.

The contract other modules rely on: `parse_paragraphs` returns `Paragraph` objects whose
`start_line`/`end_line` are 1-indexed against the *original* file, so Findings can point
back at the real source location. When a ``line_map`` is provided (from
``resolve_includes``), each paragraph's ``file`` and line numbers are translated to the
file the content actually came from — so a finding inside ``sections/intro.tex`` renders
with that path, not the top-level ``main.tex``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from qalmsw.parse.includes import LineMapEntry

_COMMENT_RE = re.compile(r"(?<!\\)%.*")
_BEGIN_DOC_RE = re.compile(r"\\begin\{document\}")
_END_DOC_RE = re.compile(r"\\end\{document\}")
_THEBIB_RE = re.compile(r"\\begin\{thebibliography\}")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?")
_WORD_RE = re.compile(r"[A-Za-z]{3,}")


@dataclass(frozen=True)
class Paragraph:
    text: str
    start_line: int
    end_line: int
    file: Path | None = None


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
    # Papers using inline \begin{thebibliography} embed ~hundreds of \bibitem entries in
    # the body. That's reference metadata, not prose the grammar/reviewer should see.
    bib = _THEBIB_RE.search(source, offset, end_offset)
    if bib:
        end_offset = bib.start()
    start_line = source.count("\n", 0, offset) + 1
    return source[offset:end_offset], start_line


def parse_paragraphs(
    source: str,
    *,
    line_map: list[LineMapEntry] | None = None,
    default_file: Path | None = None,
) -> list[Paragraph]:
    """Split the document body into blank-line-separated paragraphs.

    If ``line_map`` is provided (as produced by ``resolve_includes``), each paragraph
    is tagged with the file it originated from and its line numbers are translated
    into that file's numbering. Paragraphs are attributed to the file their first
    line belongs to; if a paragraph straddles an ``\\input{}`` boundary, the tail
    lines' original file is discarded (rare in practice; ``\\input{}`` usually sits
    on its own line, producing a paragraph break).
    """
    body, body_start_line = extract_body(source)
    stripped = _strip_comments(body)
    lines = stripped.splitlines()

    paragraphs: list[Paragraph] = []
    buf: list[str] = []
    buf_start: int | None = None

    def _origin(combined_line: int) -> tuple[Path | None, int]:
        if line_map is None:
            return default_file, combined_line
        idx = combined_line - 1
        if 0 <= idx < len(line_map):
            entry = line_map[idx]
            return entry.file, entry.line
        return default_file, combined_line

    def flush(end_line: int) -> None:
        if not buf:
            return
        text = "\n".join(buf).strip()
        if text:
            file, start = _origin(buf_start)
            _, end = _origin(end_line)
            paragraphs.append(
                Paragraph(text=text, start_line=start, end_line=end, file=file)
            )
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
