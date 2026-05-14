"""JSON report output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qalmsw.checkers import Finding


def render_findings_json(file: Path, findings: list[Finding]) -> str:
    """Return findings as a JSON string, one object with file info and results list.

    Structure:
    {
      "file": "paper.tex",
      "total": 3,
      "by_severity": {"error": 1, "warning": 1, "info": 1},
      "findings": [ ... Finding.dict() ... ]
    }
    """
    by_severity: dict[str, int] = {}
    for f in findings:
        by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1

    payload: dict[str, Any] = {
        "file": str(file),
        "total": len(findings),
        "by_severity": by_severity,
        "findings": [_finding_dict(f) for f in findings],
    }
    return json.dumps(payload, indent=2, default=str)


def _finding_dict(f: Finding) -> dict[str, Any]:
    d: dict[str, Any] = {
        "checker": f.checker,
        "severity": f.severity.value,
        "line": f.line,
        "message": f.message,
    }
    if f.suggestion is not None:
        d["suggestion"] = f.suggestion
    if f.excerpt is not None:
        d["excerpt"] = f.excerpt
    if f.file is not None:
        d["file"] = str(f.file)
    return d
