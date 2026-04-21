"""Split a .tex body into `\\section{}`-bounded sections.

Used by the reviewer checker, which wants coarse section-level chunks rather than
individual paragraphs. If the document has no `\\section{}`, the whole body is returned
as a single untitled section. When a ``line_map`` is provided, each section's ``file``
and line numbers are translated back to the file the ``\\section{}`` command was
declared in (e.g. ``sections/intro.tex`` when pulled in via ``\\input``).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from qalmsw.parse.includes import LineMapEntry
from qalmsw.parse.tex import _COMMENT_RE, extract_body

_SECTION_RE = re.compile(r"\\section\*?\s*\{([^}]*)\}")


@dataclass(frozen=True)
class Section:
    title: str
    text: str
    start_line: int
    end_line: int
    file: Path | None = None


def parse_sections(
    source: str,
    *,
    line_map: list[LineMapEntry] | None = None,
    default_file: Path | None = None,
) -> list[Section]:
    body, body_start_line = extract_body(source)
    body = _COMMENT_RE.sub("", body)

    def _origin(combined_line: int) -> tuple[Path | None, int]:
        if line_map is None:
            return default_file, combined_line
        idx = combined_line - 1
        if 0 <= idx < len(line_map):
            entry = line_map[idx]
            return entry.file, entry.line
        return default_file, combined_line

    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        total_lines = body.count("\n")
        file, start = _origin(body_start_line)
        _, end = _origin(body_start_line + total_lines)
        return [
            Section(
                title="",
                text=body.strip(),
                start_line=start,
                end_line=end,
                file=file,
            )
        ]

    sections: list[Section] = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start_combined = body_start_line + body.count("\n", 0, match.start())
        end_offset = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        end_combined = body_start_line + body.count("\n", 0, end_offset)
        text = body[match.start() : end_offset].strip()
        file, start = _origin(start_combined)
        _, end = _origin(end_combined)
        sections.append(
            Section(title=title, text=text, start_line=start, end_line=end, file=file)
        )
    return sections
