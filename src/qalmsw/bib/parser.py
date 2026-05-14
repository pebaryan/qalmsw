"""BibTeX entry extractor.

We do two passes so failures in one don't cascade into the other:

1. A regex sweep over ``@type{key,`` headers gives us the authoritative set of entries
   with source line numbers. These drive MISSING / UNUSED / DUPLICATE findings in the
   citation checker and must stay robust against malformed fields.

2. ``bibtexparser`` pulls the ``title`` (and ``author``) fields, keyed by the entry
   key. Titles are needed for the claims checker (title → Scholar lookup). When the
   library fails or skips an entry, we fall back to empty strings — the entry is still
   present for citation checks.

Comment blocks (``@comment{...}`` and ``%``-line comments) are stripped before either
pass so entries declared inside them aren't picked up.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
from bibtexparser.bparser import BibTexParser

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
    title: str = ""
    author: str = ""
    eprint: str = ""
    doi: str = ""


def _strip_line_comments_preserve_lines(text: str) -> str:
    return _LINE_COMMENT_RE.sub("", text)


def _extract_fields(text: str) -> dict[str, dict[str, str]]:
    """Return ``{entry_key: {'title': ..., 'author': ...}}``.

    Returns an empty map on any bibtexparser failure; callers should treat missing
    keys as having empty-string values.
    """
    try:
        parser = BibTexParser(common_strings=True)
        parser.ignore_nonstandard_types = False
        db = bibtexparser.loads(text, parser=parser)
    except Exception:
        return {}
    fields: dict[str, dict[str, str]] = {}
    for raw in db.entries:
        key = (raw.get("ID") or "").strip()
        if not key:
            continue
        fields[key] = {
            "title": _clean_value(raw.get("title", "")),
            "author": _clean_value(raw.get("author", "")),
            "eprint": _clean_value(raw.get("eprint", "")),
            "doi": _clean_value(raw.get("doi", "")),
        }
    return fields


def _clean_value(value: str) -> str:
    # BibTeX values often arrive with surrounding braces (`{Attention Is All...}`) and
    # line breaks from continuation; flatten to a single line of readable text.
    return " ".join(value.replace("{", "").replace("}", "").split())


def parse_bib_text(text: str, source: Path) -> list[BibEntry]:
    cleaned = _strip_line_comments_preserve_lines(text)
    fields = _extract_fields(cleaned)
    entries: list[BibEntry] = []
    for match in _ENTRY_START_RE.finditer(cleaned):
        entry_type = match.group(1).lower()
        if entry_type in _SKIPPABLE_TYPES:
            continue
        key = match.group(2).strip()
        line = cleaned.count("\n", 0, match.start()) + 1
        extra = fields.get(key, {})
        entries.append(
            BibEntry(
                key=key,
                entry_type=entry_type,
                file=source,
                line=line,
                title=extra.get("title", ""),
                author=extra.get("author", ""),
                eprint=extra.get("eprint", ""),
                doi=extra.get("doi", ""),
            )
        )
    return entries


def parse_bib_file(path: Path) -> list[BibEntry]:
    return parse_bib_text(path.read_text(encoding="utf-8"), source=path)
