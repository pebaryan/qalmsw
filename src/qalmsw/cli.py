"""`qalmsw` command-line entry point."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from qalmsw import __version__
from qalmsw.checkers import Finding, GrammarChecker
from qalmsw.llm import LlamaCppClient
from qalmsw.parse import parse_paragraphs
from qalmsw.report import render_findings

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def version() -> None:
    """Print the qalmsw version."""
    console.print(__version__)


@app.command()
def check(
    file: Path = typer.Argument(..., exists=True, readable=True, help="Path to a .tex file"),
    base_url: str | None = typer.Option(None, "--base-url", envvar="QALMSW_BASE_URL"),
    model: str | None = typer.Option(None, "--model", envvar="QALMSW_MODEL"),
) -> None:
    """Run QA checks on a LaTeX document."""
    source = file.read_text(encoding="utf-8")
    paragraphs = parse_paragraphs(source)

    llm = LlamaCppClient(base_url=base_url, model=model)
    checkers = [GrammarChecker(llm)]

    findings: list[Finding] = []
    for c in checkers:
        findings.extend(c.check(paragraphs))

    render_findings(console, file, findings)
    raise typer.Exit(code=1 if findings else 0)
