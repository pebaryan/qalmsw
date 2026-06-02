"""Gradio frontend for Hugging Face Spaces."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import gradio as gr

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
    MathChecker,
    ReferenceChecker,
    ReviewerChecker,
)
from qalmsw.document import Document
from qalmsw.llm import LlamaCppClient
from qalmsw.report.json import findings_payload
from qalmsw.retrieval import set_backend

_GRAPHICS_RE = re.compile(r"\\includegraphics(?:\s*\[[^\]]*\])?\s*\{([^}]+)\}")

_SAMPLE = r"""\documentclass{article}
\begin{document}
\section{Results}
As an AI language model, I cannot verify these numbers.

Prior work established the result \cite{missingref}.

\begin{figure}
\includegraphics{figures/result.png}
\caption{Insert caption here}
\label{fig:result}
\end{figure}
\end{document}
"""

_THEME = gr.themes.Soft(primary_hue="teal", neutral_hue="slate")
_CSS = """
.status-pill {
    border: 1px solid #d6d3d1;
    border-radius: 8px;
    padding: 6px 10px;
    display: inline-block;
    background: #fafaf9;
}
"""


def check_manuscript(
    tex_file: str | None,
    tex_source: str | None,
    bib_files: list[str] | None,
    bib_source: str | None,
    project_files: list[str] | None,
    verify_references: bool,
    run_grammar: bool,
    run_math: bool,
    run_reviewer: bool,
    run_claims: bool,
    retrieval_backend: str,
    concurrency: int,
    llm_base_url: str | None,
    llm_model: str | None,
    llm_api_key: str | None,
) -> tuple[str, list[list[Any]], dict[str, Any]]:
    """Run qalmsw checks from uploaded or pasted manuscript content."""
    with tempfile.TemporaryDirectory(prefix="qalmsw-space-") as tmp:
        tmp_dir = Path(tmp)
        main_path, source = _prepare_main_tex(tmp_dir, tex_file, tex_source)
        _copy_project_files(tmp_dir, project_files or [], source)
        bib_paths = _prepare_bib_files(tmp_dir, bib_files or [], bib_source)

        doc = Document.load(main_path)
        bib_entries = _load_bib_entries(bib_paths)
        notes: list[str] = [f"Parsed {len(doc.paragraphs)} paragraph(s)."]

        if not bib_entries:
            inline_entries = extract_inline_bibitems(
                doc.source,
                line_map=doc.line_map,
                default_file=doc.path,
            )
            if inline_entries:
                bib_entries = inline_entries
                notes.append(f"Loaded {len(inline_entries)} inline bibliography item(s).")
            else:
                notes.append("No bibliography entries found; citation checks are limited.")
        elif bib_paths:
            notes.append(f"Loaded {len(bib_entries)} bibliography entry/entries.")

        set_backend(retrieval_backend)
        checkers = _build_checkers(
            bib_entries=bib_entries,
            verify_references=verify_references,
            run_grammar=run_grammar,
            run_math=run_math,
            run_reviewer=run_reviewer,
            run_claims=run_claims,
            concurrency=concurrency,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_api_key=llm_api_key,
            notes=notes,
        )

        findings: list[Finding] = []
        for checker in checkers:
            findings.extend(checker.check(doc))

        payload = findings_payload(main_path, findings)
        return _summary(payload, notes), _finding_rows(findings), payload


def _prepare_main_tex(
    tmp_dir: Path,
    tex_file: str | None,
    tex_source: str | None,
) -> tuple[Path, str]:
    source = (tex_source or "").strip()
    if source:
        path = tmp_dir / "main.tex"
        path.write_text(source + "\n", encoding="utf-8")
        return path, source
    if not tex_file:
        raise gr.Error("Upload a .tex file or paste LaTeX source.")

    upload = Path(tex_file)
    path = tmp_dir / _safe_name(upload.name, fallback="main.tex")
    shutil.copyfile(upload, path)
    return path, path.read_text(encoding="utf-8", errors="replace")


def _prepare_bib_files(tmp_dir: Path, bib_files: list[str], bib_source: str | None) -> list[Path]:
    paths: list[Path] = []
    if (bib_source or "").strip():
        path = tmp_dir / "refs.bib"
        path.write_text((bib_source or "").strip() + "\n", encoding="utf-8")
        paths.append(path)

    for upload in bib_files:
        source = Path(upload)
        target = tmp_dir / _safe_name(source.name, fallback="refs.bib")
        shutil.copyfile(source, target)
        paths.append(target)
    return paths


def _copy_project_files(tmp_dir: Path, uploads: list[str], tex_source: str) -> None:
    graphics_paths = {Path(match.group(1).strip()) for match in _GRAPHICS_RE.finditer(tex_source)}
    for upload in uploads:
        source = Path(upload)
        safe_name = _safe_name(source.name, fallback="upload")
        target = tmp_dir / safe_name
        shutil.copyfile(source, target)

        for graphics_path in graphics_paths:
            if graphics_path.name == safe_name and not graphics_path.is_absolute():
                nested_target = tmp_dir / graphics_path
                nested_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, nested_target)


def _load_bib_entries(paths: list[Path]) -> list[BibEntry]:
    entries: list[BibEntry] = []
    for path in paths:
        entries.extend(parse_bib_file(path))
    return entries


def _build_checkers(
    bib_entries: list[BibEntry],
    verify_references: bool,
    run_grammar: bool,
    run_math: bool,
    run_reviewer: bool,
    run_claims: bool,
    concurrency: int,
    llm_base_url: str | None,
    llm_model: str | None,
    llm_api_key: str | None,
    notes: list[str],
) -> list[Checker]:
    checkers: list[Checker] = [
        ArtifactChecker(),
        FigureTableChecker(),
        ImageChecker(),
        CitationChecker(bib_entries),
    ]
    if verify_references and bib_entries:
        checkers.append(ReferenceChecker(bib_entries))

    wants_llm = run_grammar or run_math or run_reviewer or run_claims
    base_url = _clean(llm_base_url) or os.environ.get("QALMSW_BASE_URL")
    model = _clean(llm_model) or os.environ.get("QALMSW_MODEL") or "local-model"
    api_key = _clean(llm_api_key) or os.environ.get("QALMSW_API_KEY")

    if wants_llm and not base_url:
        notes.append("LLM checks skipped because no backend URL was provided.")
        return checkers

    if wants_llm:
        notes.append(f"LLM checks using {base_url} with model {model}.")
        llm = LlamaCppClient(base_url=base_url, model=model, api_key=api_key)
        if run_grammar:
            checkers.append(GrammarChecker(llm, concurrency=concurrency))
        if run_math:
            checkers.append(MathChecker(llm, concurrency=concurrency))
        if run_reviewer:
            checkers.append(ReviewerChecker(llm, concurrency=concurrency))
        if run_claims:
            checkers.append(ClaimsChecker(llm, bib_entries))
    return checkers


def _summary(payload: dict[str, Any], notes: list[str]) -> str:
    by_severity = payload["by_severity"]
    parts = [
        f"Total: {payload['total']}",
        f"Errors: {by_severity.get('error', 0)}",
        f"Warnings: {by_severity.get('warning', 0)}",
        f"Info: {by_severity.get('info', 0)}",
    ]
    note_text = "\n".join(f"- {note}" for note in notes)
    return "**" + " | ".join(parts) + "**\n\n" + note_text


def _finding_rows(findings: list[Finding]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for finding in findings:
        rows.append(
            [
                finding.severity.value,
                finding.checker,
                finding.file or "",
                finding.line,
                finding.message,
                finding.suggestion or "",
            ]
        )
    return rows


def _safe_name(name: str, fallback: str) -> str:
    candidate = Path(name).name.strip()
    if not candidate or candidate in {".", ".."}:
        return fallback
    return candidate


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _llm_status() -> str:
    if os.environ.get("QALMSW_BASE_URL"):
        return "✅ LLM backend configured — all checkers available"
    return "⚠️ Deterministic checks only — enable [LLM] checkers by configuring the backend below"


with gr.Blocks(title="qalmsw", theme=_THEME, css=_CSS) as demo:
    gr.Markdown("# qalmsw")
    gr.Markdown(f"<span class='status-pill'>{_llm_status()}</span>")

    with gr.Row():
        with gr.Column(scale=5, min_width=360):
            tex_file = gr.File(label="Main .tex file", file_types=[".tex"], type="filepath")
            with gr.Accordion("LaTeX source", open=False):
                tex_source = gr.Code(label="LaTeX source", value=_SAMPLE, lines=18)
            bib_files = gr.File(
                label=".bib files",
                file_types=[".bib"],
                file_count="multiple",
                type="filepath",
            )
            with gr.Accordion("BibTeX source", open=False):
                bib_source = gr.Code(label="BibTeX source", lines=8)
            project_files = gr.File(
                label="Project files",
                file_count="multiple",
                type="filepath",
            )

        with gr.Column(scale=4, min_width=320):
            with gr.Group():
                gr.Markdown("**Always runs:** artifacts, citations, figures, images")
                gr.Markdown("### Optional checks")
                verify_references = gr.Checkbox(label="Verify arXiv IDs and DOIs", value=False)
                run_grammar = gr.Checkbox(label="Grammar [LLM]", value=False)
                run_math = gr.Checkbox(label="Math consistency [LLM]", value=False)
                run_reviewer = gr.Checkbox(label="Reviewer critique [LLM]", value=False)
                run_claims = gr.Checkbox(label="Claim support [LLM]", value=False)
                retrieval_backend = gr.Dropdown(
                    label="Retrieval backend",
                    choices=["semantic-scholar", "google-scholar"],
                    value="semantic-scholar",
                )
                concurrency = gr.Slider(
                    label="Concurrency",
                    minimum=1,
                    maximum=8,
                    step=1,
                    value=1,
                )
            with gr.Accordion("LLM backend config", open=False):
                gr.Markdown(
                "Set `QALMSW_BASE_URL` and `QALMSW_MODEL` as Space secrets"
                " to enable [LLM] checkers."
            )
                llm_base_url = gr.Textbox(
                    label="Base URL",
                    placeholder="https://api.openai.com/v1",
                )
                llm_model = gr.Textbox(
                    label="Model",
                    placeholder="provider-model-id or local-model",
                )
                llm_api_key = gr.Textbox(
                    label="API key",
                    type="password",
                    placeholder="Optional; leave blank to use Space secret",
                )
            run = gr.Button("Run checks", variant="primary")
            gr.Markdown(
                "Upload a .tex file (or paste source) and optional .bib files, "
                "then click **Run checks**. Always-on checks run automatically; "
                "toggle optional checks above. Results appear below.",
            )

    summary = gr.Markdown()
    findings_table = gr.DataFrame(
        headers=["Severity", "Checker", "File", "Line", "Message", "Suggestion"],
        datatype=["str", "str", "str", "number", "str", "str"],
        interactive=False,
        wrap=True,
    )
    json_output = gr.JSON(label="JSON")

    tex_file.change(
        lambda path: Path(path).read_text(encoding="utf-8", errors="replace") if path else _SAMPLE,
        inputs=[tex_file],
        outputs=[tex_source],
    )
    def _read_bib_files(paths):
        if not paths:
            return ""
        return "\n\n".join(
            Path(p).read_text(encoding="utf-8", errors="replace") for p in paths
        )

    bib_files.change(
        _read_bib_files,
        inputs=[bib_files],
        outputs=[bib_source],
    )

    run.click(
        check_manuscript,
        inputs=[
            tex_file,
            tex_source,
            bib_files,
            bib_source,
            project_files,
            verify_references,
            run_grammar,
            run_math,
            run_reviewer,
            run_claims,
            retrieval_backend,
            concurrency,
            llm_base_url,
            llm_model,
            llm_api_key,
        ],
        outputs=[summary, findings_table, json_output],
    )


if __name__ == "__main__":
    demo.queue().launch()
