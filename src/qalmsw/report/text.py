"""Human-readable terminal report."""
from __future__ import annotations

from pathlib import Path

from rich.console import Console

from qalmsw.checkers import Finding, Severity

_SEVERITY_STYLE = {
    Severity.info: "dim",
    Severity.warning: "yellow",
    Severity.error: "red bold",
}


def render_findings(console: Console, file: Path, findings: list[Finding]) -> None:
    if not findings:
        console.print(f"[green]{file}[/]: no issues found")
        return

    for f in sorted(findings, key=lambda f: (f.file or "", f.line, f.checker)):
        style = _SEVERITY_STYLE[f.severity]
        loc = f"{f.file or file}:{f.line}"
        console.print(
            f"[{style}]{f.severity.value}[/] [dim]{loc}[/] "
            f"[cyan]{f.checker}[/] {f.message}"
        )
        if f.excerpt:
            console.print(f"    [dim]>[/] {f.excerpt}")
        if f.suggestion:
            console.print(f"    [green]suggest:[/] {f.suggestion}")

    console.print(f"\n[bold]{len(findings)}[/] issue(s)")
