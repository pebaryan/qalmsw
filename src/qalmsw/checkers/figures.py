"""Figure and Table Completeness Checker.

Scans the LaTeX source for figure and table float environments and checks:
- Every float has a \\caption{} (missing = error)
- Caption text isn't a placeholder/template (error if recognisable)
- Figure/table labels are actually \\ref{}'d somewhere in the body (warning if orphaned)
- No empty float environments (warning)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document

# ---------------------------------------------------------------------------
# Float extraction
# ---------------------------------------------------------------------------

_FLOAT_RE = re.compile(
    r"\\begin\{(figure|table)(?:\*)?\}\s+"
    r"(.*?)\s+"
    r"\\end\{\1(?:\*)?\}",
    re.DOTALL,
)

_CAPTION_RE = re.compile(r"\\caption\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", re.DOTALL)
_LABEL_RE = re.compile(r"\\label\s*\{([^}]*)\}", re.DOTALL)
_REF_RE = re.compile(r"\\ref\s*\{([^}]*)\}", re.DOTALL)

# Placeholder caption text patterns (same philosophy as artifacts checker)
_PLACEHOLDER_CAPTION_RE = re.compile(
    r"(?:placeholder|draft|template|add\s+caption|"
    r"caption\s+(?:text|here|goes\s+here)|"
    r"your\s+caption\s+(?:here|text)|"
    r"insert\s+caption|"
    r"todo\s*:?\s*add\s+caption|"
    r"illustrative|"
    r"sample\s+data|"
    r"figure\s+\d+\s+about\s+here|"
    r"table\s+\d+\s+about\s+here)",
    re.IGNORECASE,
)


@dataclass
class FloatDef:
    env_type: str  # "figure" or "table"
    content: str
    start_line: int
    end_line: int
    caption: str | None = None
    labels: list[str] = field(default_factory=list)


def _extract_floats(source: str, body_start_line: int) -> list[FloatDef]:
    """Find figure/table environments. Returns (type, content, line, caption, labels)."""
    floats: list[FloatDef] = []
    for match in _FLOAT_RE.finditer(source):
        env_type = match.group(1)
        content = match.group(2)
        start_line = source[: match.start()].count("\n") + body_start_line
        end_line = source[: match.end()].count("\n") + body_start_line

        # Extract caption
        cap_match = _CAPTION_RE.search(content)
        caption = cap_match.group(1).strip() if cap_match else None

        # Extract all labels
        labels = [m.group(1).strip() for m in _LABEL_RE.finditer(content)]

        floats.append(
            FloatDef(
                env_type=env_type,
                content=content,
                start_line=start_line,
                end_line=end_line,
                caption=caption,
                labels=labels,
            )
        )
    return floats


def _collect_all_refs(source: str) -> set[str]:
    """Collect all \\ref{} values anywhere in the source."""
    return {m.group(1).strip() for m in _REF_RE.finditer(source)}


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class FigureTableChecker:
    """Checks figure and table environments for completeness.

    Deterministic (no LLM calls), runs on every check.
    """

    name = "figures"

    def check(self, doc: Document) -> list[Finding]:
        findings: list[Finding] = []

        floats = _extract_floats(doc.source, 1)
        if not floats:
            return findings

        all_refs = _collect_all_refs(doc.source)

        for fl in floats:
            # 1. Missing caption
            if fl.caption is None:
                findings.append(
                    Finding(
                        checker=self.name,
                        severity=Severity.error,
                        line=fl.start_line,
                        message=f"{fl.env_type} is missing a \\caption{{}}",
                        suggestion="Add a descriptive caption to this float.",
                    )
                )
            else:
                # 2. Placeholder caption text
                if _PLACEHOLDER_CAPTION_RE.search(fl.caption):
                    findings.append(
                        Finding(
                            checker=self.name,
                            severity=Severity.error,
                            line=fl.start_line,
                            message=(
                                f"{fl.env_type} has placeholder caption: "
                                f"{fl.caption[:60]}"
                            ),
                            excerpt=fl.caption[:80],
                            suggestion="Replace with a real, descriptive caption.",
                        )
                    )

            # 3. Orphaned label (defined but never \\ref{}'d)
            for label in fl.labels:
                if label not in all_refs:
                    findings.append(
                        Finding(
                            checker=self.name,
                            severity=Severity.warning,
                            line=fl.start_line,
                            message=(
                                f"{fl.env_type} label '{label}' is not "
                                f"referenced by any \\ref{{}} in the text"
                            ),
                            suggestion=(
                                f"Add a \\ref{{{label}}} where you discuss "
                                f"this {fl.env_type} in the body, or remove the label."
                            ),
                        )
                    )

            # 4. Empty float (no real content)
            # Check for things that count as "real" content
            has_image = bool(re.search(r"\\includegraphics", fl.content))
            has_tabular = bool(
                re.search(
                    r"\\begin\{(?:tabular|tabularx|tabulary|longtable|array)\}",
                    fl.content,
                )
            )
            has_diagram = bool(
                re.search(
                    r"\\begin\{(?:tikzpicture|pgfpicture|asy|pspicture)\}",
                    fl.content,
                )
            )
            has_verbatim_input = bool(
                re.search(r"(?:\\lstinputlisting|\\input|\\import)\s*\{", fl.content)
            )

            if not (has_image or has_tabular or has_diagram or has_verbatim_input):
                # Double-check: strip all LaTeX commands and see if anything remains
                stripped = re.sub(
                    r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^}]*\})?",
                    "",
                    fl.content,
                ).strip()
                if not stripped or len(stripped.split()) < 2:
                    env_display = f"{fl.env_type} at line {fl.start_line}"
                    findings.append(
                        Finding(
                            checker=self.name,
                            severity=Severity.warning,
                            line=fl.start_line,
                            message=f"Near-empty {env_display}: no meaningful content",
                            suggestion="Add content (image, table, or diagram) to this float.",
                        )
                    )

        return findings
