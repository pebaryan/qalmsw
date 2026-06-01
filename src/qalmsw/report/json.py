"""JSON report output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qalmsw.checkers import Finding


def findings_payload(file: Path, findings: list[Finding]) -> dict[str, Any]:
    """Return the serializable JSON payload for one checked file."""
    by_severity: dict[str, int] = {}
    for f in findings:
        by_severity[f.severity.value] = by_severity.get(f.severity.value, 0) + 1

    return {
        "file": str(file),
        "total": len(findings),
        "by_severity": by_severity,
        "findings": [_finding_dict(f) for f in findings],
    }


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
    return json.dumps(findings_payload(file, findings), indent=2, default=str)


def render_batch_findings_json(results: list[tuple[Path, list[Finding]]]) -> str:
    """Return parseable JSON for one or more checked files.

    Single-file output preserves the original object shape. Multi-file output wraps
    per-file payloads in a top-level summary object.
    """
    if len(results) == 1:
        file, findings = results[0]
        return render_findings_json(file, findings)

    files = [findings_payload(file, findings) for file, findings in results]
    by_severity: dict[str, int] = {}
    for file_payload in files:
        for severity, count in file_payload["by_severity"].items():
            by_severity[severity] = by_severity.get(severity, 0) + count

    payload = {
        "total_files": len(results),
        "total": sum(file_payload["total"] for file_payload in files),
        "by_severity": by_severity,
        "files": files,
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
