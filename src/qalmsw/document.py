"""The unit of input every checker operates on.

`Document` bundles the .tex path, full source, and parsed paragraphs so individual
checkers don't each re-parse the file and can choose which level of detail to consume
(raw source for citation scanning, paragraphs for grammar, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qalmsw.parse import Paragraph, parse_paragraphs


@dataclass(frozen=True)
class Document:
    path: Path
    source: str
    paragraphs: list[Paragraph]

    @classmethod
    def load(cls, path: Path) -> Document:
        source = path.read_text(encoding="utf-8")
        return cls(path=path, source=source, paragraphs=parse_paragraphs(source))
