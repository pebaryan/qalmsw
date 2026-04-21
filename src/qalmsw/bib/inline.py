"""Extract ``\\bibitem{}`` entries from inline ``\\begin{thebibliography}`` blocks.

Many papers ship a pre-formatted bibliography inside the .tex body instead of a
separate .bib file. We scan those blocks into ``BibEntry`` objects so the citation
checker can still cross-check ``\\cite`` keys without the user having to point at a
.bib file by hand.

Only the entry key + source line are reliable. We take a best-effort stab at the
title (the first "quoted" or ``\\textit/\\emph``-wrapped chunk after the author list),
but the citation checker doesn't need it; the claims checker does, and it tolerates
empty titles by degrading to an ``info`` finding.
"""
from __future__ import annotations

import re
from pathlib import Path

from qalmsw.bib.parser import BibEntry
from qalmsw.parse.includes import LineMapEntry

_THEBIB_BLOCK_RE = re.compile(
    r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
    re.DOTALL,
)
_BIBITEM_RE = re.compile(
    r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}",
)
_TITLE_QUOTED_RE = re.compile(r"``([^']+?)''|\"([^\"]+?)\"")
_TITLE_MACRO_RE = re.compile(r"\\(?:textit|emph|textbf)\s*\{([^}]+)\}")


def extract_inline_bibitems(
    source: str,
    *,
    line_map: list[LineMapEntry] | None = None,
    default_file: Path | None = None,
) -> list[BibEntry]:
    """Return a ``BibEntry`` per ``\\bibitem`` found inside a ``thebibliography`` block.

    When ``line_map`` is provided, each entry's ``file`` and ``line`` are translated
    back to the file that declared them (useful when the bibliography lives in a
    ``\\input``-ed file).
    """
    entries: list[BibEntry] = []

    def _origin(combined_line: int) -> tuple[Path, int]:
        if line_map is not None:
            idx = combined_line - 1
            if 0 <= idx < len(line_map):
                e = line_map[idx]
                return e.file, e.line
        return (default_file or Path("<source>")), combined_line

    for block in _THEBIB_BLOCK_RE.finditer(source):
        block_text = block.group(0)
        block_start = block.start()
        # Find bibitems and the text that follows each up to the next bibitem.
        items = list(_BIBITEM_RE.finditer(block_text))
        for i, match in enumerate(items):
            key = match.group(1).strip()
            if not key:
                continue
            combined_line = source.count("\n", 0, block_start + match.start()) + 1
            file, line = _origin(combined_line)
            body_end = items[i + 1].start() if i + 1 < len(items) else len(block_text)
            body = block_text[match.end():body_end]
            title = _guess_title(body)
            entries.append(
                BibEntry(
                    key=key,
                    entry_type="bibitem",
                    file=file,
                    line=line,
                    title=title,
                )
            )
    return entries


def _guess_title(body: str) -> str:
    """Best-effort title guess from a \\bibitem body.

    Look for a ``...''-quoted or \\textit/\\emph/\\textbf-wrapped run first; fall back
    to empty. We don't try to be clever — getting the title wrong is fine (claims
    degrades gracefully), getting the key wrong would be a bug.
    """
    m = _TITLE_QUOTED_RE.search(body)
    if m:
        return (m.group(1) or m.group(2) or "").strip()
    m = _TITLE_MACRO_RE.search(body)
    if m:
        return m.group(1).strip()
    return ""
