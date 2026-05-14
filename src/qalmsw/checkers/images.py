"""Image file existence checker.

Scans for ``\\includegraphics`` commands in the LaTeX source and verifies
the referenced image files exist on disk relative to the document directory.

Missing images are a common sign of uncurated LLM output — the model generates
``\\includegraphics{results.png}`` without actually having created the file.

Tries common image extensions (.pdf, .png, .jpg, .jpeg, .eps, .svg) when
no extension is present.
"""

from __future__ import annotations

import re
from pathlib import Path

from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document

_GRAPHICS_RE = re.compile(
    r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}"
)

_COMMON_EXTENSIONS: tuple[str, ...] = (
    ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg", ".gif", ".tiff",
)

# Extensions that aren't image files — skip these
_SKIP_EXTENSIONS: tuple[str, ...] = (".tex", ".cls", ".sty", ".bib", ".bst")


class ImageChecker:
    """Checks that all \\includegraphics files exist relative to the document."""

    name = "images"

    def check(self, doc: Document) -> list[Finding]:
        findings: list[Finding] = []
        doc_dir = doc.path.parent

        for match in _GRAPHICS_RE.finditer(doc.source):
            raw_path = match.group(1).strip()
            if not raw_path:
                continue

            line = doc.source[: match.start()].count("\n") + 1

            # Skip obviously not-image paths
            if any(raw_path.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            resolved = _resolve_image(doc_dir, raw_path)
            if resolved is None:
                findings.append(
                    Finding(
                        checker=self.name,
                        severity=Severity.error,
                        line=line,
                        message=f"Image file not found: '{raw_path}'",
                        excerpt=raw_path[:80],
                        suggestion=(
                            f"Place the image at "
                            f"\\includegraphics{{{_suggest_path(doc_dir, raw_path)}}} "
                            f"or remove this reference."
                        ),
                    )
                )

        return findings


def _resolve_image(doc_dir: Path, raw_path: str) -> Path | None:
    """Resolve an \\includegraphics path to an existing file, or None.

    Tries the path as-is first, then with common extensions appended.
    """
    candidate = (doc_dir / raw_path).resolve()

    # Try exact path first
    if candidate.exists():
        return candidate

    # Try without extension if one is present
    if candidate.suffix:
        # Maybe the referenced path has an extension that doesn't match the actual file
        # Try stripping the extension and re-adding common ones
        stem = candidate.with_suffix("")
        for ext in _COMMON_EXTENSIONS:
            trial = stem.with_suffix(ext)
            if trial.exists():
                return trial
    else:
        # No extension — try all common ones
        for ext in _COMMON_EXTENSIONS:
            trial = candidate.with_suffix(ext)
            if trial.exists():
                return trial

    return None


def _suggest_path(doc_dir: Path, raw_path: str) -> str:
    """Return a suggested path hint for the error message."""
    for ext in _COMMON_EXTENSIONS:
        trial = (doc_dir / raw_path).with_suffix(ext)
        if trial.exists():
            return str(trial.relative_to(doc_dir))
    return raw_path
