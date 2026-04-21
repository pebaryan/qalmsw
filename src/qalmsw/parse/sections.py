"""Split a .tex body into `\\section{}`-bounded sections.

Used by the reviewer checker, which wants coarse section-level chunks rather than
individual paragraphs. If the document has no `\\section{}`, the whole body is returned
as a single untitled section.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from qalmsw.parse.tex import _COMMENT_RE, extract_body

_SECTION_RE = re.compile(r"\\section\*?\s*\{([^}]*)\}")


@dataclass(frozen=True)
class Section:
    title: str
    text: str
    start_line: int
    end_line: int


def parse_sections(source: str) -> list[Section]:
    body, body_start_line = extract_body(source)
    body = _COMMENT_RE.sub("", body)

    matches = list(_SECTION_RE.finditer(body))
    if not matches:
        total_lines = body.count("\n")
        return [
            Section(
                title="",
                text=body.strip(),
                start_line=body_start_line,
                end_line=body_start_line + total_lines,
            )
        ]

    sections: list[Section] = []
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start_line = body_start_line + body.count("\n", 0, match.start())
        end_offset = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        end_line = body_start_line + body.count("\n", 0, end_offset)
        text = body[match.start() : end_offset].strip()
        sections.append(
            Section(title=title, text=text, start_line=start_line, end_line=end_line)
        )
    return sections
