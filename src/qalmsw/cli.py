"""`qalmsw` command-line entry point."""
from __future__ import annotations

from glob import glob
from pathlib import Path

import typer
from rich.console import Console

from qalmsw import __version__
from qalmsw.bib import BibEntry, extract_inline_bibitems, parse_bib_file
from qalmsw.checkers import (
    ArtifactChecker,
    Checker,
    CitationChecker,
    ClaimsChecker,
    FigureTableChecker,
    Finding,
    GrammarChecker,
    ImageChecker,
    ReferenceChecker,
    ReviewerChecker,
)
from qalmsw.document import Document
from qalmsw.llm import LlamaCppClient
from qalmsw.parse import scan_bib_resources
from qalmsw.report import render_findings, render_findings_json
from qalmsw.retrieval import search_by_title, set_backend

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def version() -> None:
    """Print the qalmsw version."""
    console.print(__version__)


@app.command()
def check(
    files: list[Path] = typer.Argument(
        ...,
        help="Path(s) to .tex file(s). Supports glob patterns (e.g. src/**/*.tex).",
    ),
    bib: list[Path] = typer.Option(
        [],
        "--bib",
        help="Explicit .bib file(s). If omitted, .bib files are auto-discovered from "
        "\\bibliography{} / \\addbibresource{} declarations.",
    ),
    skip_grammar: bool = typer.Option(False, "--skip-grammar", help="Skip LLM grammar checker"),
    skip_reviewer: bool = typer.Option(False, "--skip-reviewer", help="Skip LLM reviewer checker"),
    enable_claims: bool = typer.Option(
        False,
        "--enable-claims",
        help="Enable claim-to-reference check via Semantic Scholar.",
    ),
    retrieval: str = typer.Option(
        "semantic-scholar",
        "--retrieval",
        help="Retrieval backend for --enable-claims: 'semantic-scholar' (default, free API) "
        "or 'google-scholar' (scraping, may hit CAPTCHAs).",
    ),
    concurrency: int = typer.Option(
        1,
        "--concurrency",
        "-j",
        min=1,
        help="Number of parallel LLM requests. Match your llama.cpp server's --parallel N.",
    ),
    base_url: str | None = typer.Option(None, "--base-url", envvar="QALMSW_BASE_URL"),
    model: str | None = typer.Option(None, "--model", envvar="QALMSW_MODEL"),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON (for CI integration).",
    ),
) -> None:
    """Run QA checks on one or more LaTeX documents."""
    resolved = _resolve_files(files)
    if not resolved:
        console.print("[red]error[/]: no .tex files found matching the given paths")
        raise typer.Exit(code=1)

    # Select retrieval backend for claims checker
    set_backend(retrieval)

    if len(resolved) > 1:
        console.print(f"[dim]{len(resolved)} file(s) to check[/]")

    any_errors = False
    for file in resolved:
        if not json_output:
            if len(resolved) > 1:
                console.print(f"\n[bold]{file}[/]")
            else:
                console.print(f"[bold]{file}[/]")

        has_errors = _check_single(
            file, bib, skip_grammar, skip_reviewer, enable_claims,
            concurrency, base_url, model, json_output,
        )
        if has_errors:
            any_errors = True

    raise typer.Exit(code=1 if any_errors else 0)


def _check_single(
    file: Path,
    bib: list[Path],
    skip_grammar: bool,
    skip_reviewer: bool,
    enable_claims: bool,
    concurrency: int,
    base_url: str | None,
    model: str | None,
    json_output: bool,
) -> bool:
    """Run checks on a single file. Returns True if any errors found."""
    doc = Document.load(file)
    console.print(f"[dim]{len(doc.paragraphs)} paragraph(s) parsed[/]")

    bib_paths = list(bib) if bib else _discover_bib_files(doc)
    bib_entries = _load_bib_entries(bib_paths)
    if bib_paths:
        console.print(f"[dim]{len(bib_entries)} bib entries from {len(bib_paths)} file(s)[/]")
    if not bib_entries:
        inline = extract_inline_bibitems(
            doc.source, line_map=doc.line_map, default_file=doc.path
        )
        if inline:
            bib_entries = inline
            console.print(
                f"[dim]{len(inline)} bib entries from inline "
                f"\\begin{{thebibliography}}[/]"
            )
        else:
            console.print(
                "[yellow]warning[/]: no bib entries found (no --bib, no \\bibliography{}, "
                "no inline \\begin{thebibliography}); citation checks will be limited."
            )

    checkers: list[Checker] = [
        ArtifactChecker(),
        FigureTableChecker(),
        ImageChecker(),
        CitationChecker(bib_entries),
    ]
    if bib_entries:
        checkers.append(ReferenceChecker(bib_entries))
    if not skip_grammar or not skip_reviewer or enable_claims:
        llm = LlamaCppClient(base_url=base_url, model=model)
        if not skip_grammar:
            checkers.append(GrammarChecker(llm, concurrency=concurrency))
        if not skip_reviewer:
            checkers.append(ReviewerChecker(llm, concurrency=concurrency))
        if enable_claims:
            checkers.append(ClaimsChecker(llm, bib_entries))

    findings: list[Finding] = []
    for c in checkers:
        findings.extend(c.check(doc))

    if json_output:
        console.print(render_findings_json(file, findings))
    else:
        render_findings(console, file, findings)

    return any(f.severity.value == "error" for f in findings)


@app.command()
def scholar(
    query: list[str] = typer.Argument(..., help="Title query (may be unquoted)"),
) -> None:
    """Look up the first Semantic Scholar match for a title query.

    Default backend is Semantic Scholar (free API, no CAPTCHAs).
    Use --retrieval google-scholar for the scraping-based backend.
    """
    text = " ".join(query)
    result = search_by_title(text)
    if result is None:
        console.print(f"[yellow]no match for:[/] {text}")
        raise typer.Exit(code=1)
    console.print(f"[bold]title:[/]    {result.title}")
    console.print(f"[bold]authors:[/]  {', '.join(result.authors) or '(unknown)'}")
    console.print(f"[bold]year:[/]     {result.year if result.year is not None else '(unknown)'}")
    console.print(f"[bold]url:[/]      {result.url or '(none)'}")
    console.print(f"[bold]abstract:[/] {result.abstract or '(no abstract)'}")


def _resolve_files(paths: list[Path]) -> list[Path]:
    """Expand globs and filter to existing .tex files."""
    resolved: list[Path] = []
    for p in paths:
        if p.is_file():
            resolved.append(p)
        else:
            # Try glob expansion on the string form
            for match in sorted(glob(str(p))):
                candidate = Path(match)
                if candidate.is_file() and candidate.suffix == ".tex":
                    resolved.append(candidate)
    return resolved


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



