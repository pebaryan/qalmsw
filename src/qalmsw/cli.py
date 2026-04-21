"""`qalmsw` command-line entry point."""
from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from qalmsw import __version__
from qalmsw.bib import BibEntry, parse_bib_file
from qalmsw.checkers import Checker, CitationChecker, Finding, GrammarChecker, ReviewerChecker
from qalmsw.document import Document
from qalmsw.llm import LlamaCppClient
from qalmsw.parse import scan_bib_resources
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
    bib: list[Path] = typer.Option(
        [],
        "--bib",
        help="Explicit .bib file(s). If omitted, .bib files are auto-discovered from "
        "\\bibliography{} / \\addbibresource{} declarations.",
    ),
    skip_grammar: bool = typer.Option(False, "--skip-grammar", help="Skip LLM grammar checker"),
    skip_reviewer: bool = typer.Option(False, "--skip-reviewer", help="Skip LLM reviewer checker"),
    concurrency: int = typer.Option(
        1,
        "--concurrency",
        "-j",
        min=1,
        help="Number of parallel LLM requests. Match your llama.cpp server's --parallel N.",
    ),
    base_url: str | None = typer.Option(None, "--base-url", envvar="QALMSW_BASE_URL"),
    model: str | None = typer.Option(None, "--model", envvar="QALMSW_MODEL"),
) -> None:
    """Run QA checks on a LaTeX document."""
    doc = Document.load(file)
    console.print(f"[dim]{len(doc.paragraphs)} paragraph(s) parsed[/]")

    bib_paths = list(bib) if bib else _discover_bib_files(doc)
    bib_entries = _load_bib_entries(bib_paths)
    if bib_paths:
        console.print(f"[dim]{len(bib_entries)} bib entries from {len(bib_paths)} file(s)[/]")

    checkers: list[Checker] = [CitationChecker(bib_entries)]
    if not skip_grammar or not skip_reviewer:
        llm = LlamaCppClient(base_url=base_url, model=model)
        if not skip_grammar:
            checkers.append(GrammarChecker(llm, concurrency=concurrency))
        if not skip_reviewer:
            checkers.append(ReviewerChecker(llm, concurrency=concurrency))

    findings: list[Finding] = []
    for c in checkers:
        findings.extend(c.check(doc))

    render_findings(console, file, findings)
    raise typer.Exit(code=1 if any(f.severity.value == "error" for f in findings) else 0)


def _discover_bib_files(doc: Document) -> list[Path]:
    names = scan_bib_resources(doc.source)
    base_dir = doc.path.parent
    resolved: list[Path] = []
    for name in names:
        candidate = base_dir / (name if name.endswith(".bib") else f"{name}.bib")
        if candidate.exists():
            resolved.append(candidate)
        else:
            console.print(f"[yellow]warning[/]: referenced bib file not found: {candidate}")
    return resolved


def _load_bib_entries(paths: list[Path]) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for p in paths:
        entries.extend(parse_bib_file(p))
    return entries
