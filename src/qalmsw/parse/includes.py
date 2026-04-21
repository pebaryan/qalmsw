"""Recursive ``\\input{}`` / ``\\include{}`` resolution.

LaTeX papers commonly split source across files — ``main.tex`` pulls in
``sections/intro.tex`` via ``\\input{}``. We inline those contents so downstream
parsing (paragraphs, sections) sees one contiguous body, and we carry a per-line
``LineMap`` so findings can still point at the original file + line.

The resolver is conservative:

- Only ``\\input`` and ``\\include`` are followed.
- ``\\input`` inside a ``%`` comment is ignored (we strip comments first).
- Missing include targets are replaced with empty content (so a single missing
  file doesn't abort the run); we keep a record in ``LineMapEntry`` that points
  back at the parent so downstream code has somewhere to anchor errors.
- Cycle detection: a file currently on the include stack is not re-expanded.

The relative-path convention matches what ``pdflatex`` does: includes are resolved
relative to the directory of the file that declared them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_INCLUDE_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_COMMENT_RE = re.compile(r"(?<!\\)%.*")


@dataclass(frozen=True)
class LineMapEntry:
    file: Path
    line: int  # 1-indexed inside `file`


def _resolve_target(base_dir: Path, name: str) -> Path:
    name = name.strip()
    candidate = Path(name)
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    if candidate.suffix.lower() != ".tex":
        with_tex = candidate.with_suffix(candidate.suffix + ".tex")
        if with_tex.exists():
            return with_tex
        bare = candidate.parent / (candidate.name + ".tex")
        if bare.exists():
            return bare
    return candidate


def _expand(path: Path, stack: tuple[Path, ...]) -> tuple[list[str], list[LineMapEntry]]:
    """Return ``(lines, map)`` for ``path`` with includes inlined.

    ``lines`` is a list of lines (no trailing newlines). ``map[i]`` tells you which
    (file, line) produced ``lines[i]``.
    """
    if path in stack:
        # Cycle: return the include as a literal so the check is visible, but don't recurse.
        return ([f"% qalmsw: cycle detected, not expanding {path}"], [LineMapEntry(path, 1)])
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return ([f"% qalmsw: could not read {path}"], [LineMapEntry(path, 1)])

    out_lines: list[str] = []
    out_map: list[LineMapEntry] = []
    for i, raw_line in enumerate(source.splitlines()):
        lineno = i + 1
        # Strip the comment part to detect \input but keep the original line intact otherwise.
        uncommented = _COMMENT_RE.sub("", raw_line)
        match = _INCLUDE_RE.search(uncommented)
        if match is None:
            out_lines.append(raw_line)
            out_map.append(LineMapEntry(path, lineno))
            continue
        target = _resolve_target(path.parent, match.group(1))
        child_lines, child_map = _expand(target, stack + (path,))
        out_lines.extend(child_lines)
        out_map.extend(child_map)
    return out_lines, out_map


def resolve_includes(path: Path) -> tuple[str, list[LineMapEntry]]:
    """Return ``(combined_source, line_map)`` for ``path`` with includes inlined.

    ``line_map[i]`` describes line ``i + 1`` of the combined source: which file it came
    from and the 1-indexed line number inside that file.
    """
    lines, line_map = _expand(path, stack=())
    combined = "\n".join(lines)
    if combined:
        combined += "\n"
    return combined, line_map
