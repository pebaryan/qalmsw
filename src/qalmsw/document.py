"""The unit of input every checker operates on.

`Document` bundles the .tex path, full source, and parsed paragraphs so individual
checkers don't each re-parse the file and can choose which level of detail to consume
(raw source for citation scanning, paragraphs for grammar, etc.).

``Document.source`` is the *combined* source — ``\\input{}`` / ``\\include{}`` bodies
inlined. ``Document.line_map`` lets code translate a line in ``source`` back to its
original file and line number, so findings keep pointing at the file the author edits.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from qalmsw.parse import LineMapEntry, Paragraph, parse_paragraphs, resolve_includes


@dataclass(frozen=True)
class Document:
    path: Path
    source: str
    paragraphs: list[Paragraph]
    line_map: list[LineMapEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> Document:
        source, line_map = resolve_includes(path)
        paragraphs = parse_paragraphs(source, line_map=line_map, default_file=path)
        return cls(path=path, source=source, paragraphs=paragraphs, line_map=line_map)
