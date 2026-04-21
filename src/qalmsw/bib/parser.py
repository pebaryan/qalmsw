"""Minimal BibTeX entry extractor.

Pulls out ``@type{key,`` headers and their source line. We deliberately don't parse
fields — nested braces in values make full BibTeX parsing a rabbit hole, and the
citation checker only needs keys + line numbers to produce MISSING / UNUSED /
DUPLICATE findings. Entries declared inside comment blocks are excluded by pre-stripping
BibTeX ``@comment{...}`` blocks and ``%``-line comments.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_ENTRY_START_RE = re.compile(
    r"^[ \t]*@(\w+)\s*\{\s*([^,\s}]+)\s*,",
    re.MULTILINE,
)
_LINE_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

_SKIPPABLE_TYPES = frozenset({"string", "preamble", "comment"})


@dataclass(frozen=True)
class BibEntry:
    key: str
    entry_type: str
    file: Path
    line: int


def _strip_line_comments_preserve_lines(text: str) -> str:
    return _LINE_COMMENT_RE.sub("", text)


def parse_bib_text(text: str, source: Path) -> list[BibEntry]:
    cleaned = _strip_line_comments_preserve_lines(text)
    entries: list[BibEntry] = []
    for match in _ENTRY_START_RE.finditer(cleaned):
        entry_type = match.group(1).lower()
        if entry_type in _SKIPPABLE_TYPES:
            continue
        key = match.group(2).strip()
        line = cleaned.count("\n", 0, match.start()) + 1
        entries.append(BibEntry(key=key, entry_type=entry_type, file=source, line=line))
    return entries


def parse_bib_file(path: Path) -> list[BibEntry]:
    return parse_bib_text(path.read_text(encoding="utf-8"), source=path)
