# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

qalmsw is a Python CLI that runs LLM-powered QA checks on scientific LaTeX manuscripts. The LLM backend is a **local llama.cpp server** reached via its OpenAI-compatible API; the code must never assume a hosted provider.

Target model sizes: **9B–31B GGUF** running on llama.cpp. Context windows are therefore modest (~8k–32k), so checks that reason over long stretches of text must **chunk**, not send the whole document in one call.

## Commands

```bash
pip install -e '.[dev]'     # install + dev deps
pytest -q                   # run tests (all use a FakeLLM; no network)
pytest tests/test_parse.py  # single test file
ruff check .                # lint
qalmsw check paper.tex      # run checks against a .tex file
```

The `qalmsw check` command reads `QALMSW_BASE_URL` (default `http://localhost:8080/v1`) and `QALMSW_MODEL` (default `local-model`) from the environment; both can be overridden with `--base-url` / `--model`.

## Architecture

The pipeline is **load → checkers → report**, and every checker produces a uniform `Finding` so the report/CI layer never branches on checker type.

```
.tex file (+ .bib)
   │
   ▼
Document.load                  # path + source + parse_paragraphs()
   │  Document                 #
   ▼
checkers.*                     # each implements the Checker protocol:
   │  list[Finding]            #     check(doc: Document) -> list[Finding]
   ▼
report.render_findings         # rich-formatted terminal output
```

### Contracts worth preserving

- **`Paragraph.start_line` / `end_line` are 1-indexed against the *origin* file** — for single-file docs that's the .tex itself; for multi-file docs it's whichever `\input{}`-ed file the content lives in. `Paragraph.file` (and `Section.file`, `Finding.file`) carries the origin path. Findings render with `origin:line` so editors jump to the file the author edits, not the top-level `main.tex`.
- **Comment stripping preserves newlines** so line numbers stay stable after `%`-stripping. `parse.tex._COMMENT_RE` uses a negative look-behind to skip escaped `\%`.
- **`Document.load` inlines `\input{}` / `\include{}` recursively** via `parse/includes.py::resolve_includes`, producing a combined `source` plus a per-line `LineMapEntry` list. Parsers (`parse_paragraphs`, `parse_sections`) take that map as a kwarg and translate combined-source lines back to `(origin_file, line_in_file)`. Cycles are broken; missing targets become a one-line placeholder comment so the run continues.
- **Checkers receive a `Document`**, not just paragraphs. Citation-style checkers need the raw source (cites can appear outside prose paragraphs) and the path (to resolve `.bib` files). The `Checker` protocol is `check(doc: Document) -> list[Finding]`.
- **Non-prose paragraphs are filtered by the consumer**, not at load time. `GrammarChecker` calls `has_prose()` per paragraph so citation-scanning checkers still see headings. Don't pre-filter in the CLI.
- **CLI exit code is `1` only when an `error`-severity finding exists.** `info` (unused bib entry) and `warning` (duplicate bib key) findings are non-fatal by design — drafts routinely have them.
- **`LLMClient` is a `typing.Protocol`**, not an ABC. Tests pass a `FakeLLM` that only implements `complete_json`. Don't tighten the interface into a base class; the Protocol is intentional so any object with the right shape works.
- **Checkers never ask the LLM for line numbers.** Small local models count lines unreliably. Instead they ask for an `excerpt` string and we locate it in the paragraph text (`grammar._locate_line`). New checkers should follow this pattern.
- **Structured output uses `response_format={"type": "json_object"}`** — supported by llama.cpp server. The system prompt must also spell out the JSON shape, because small models otherwise drift.
- **`LLMClient` has `max_retries=0`.** A slow local model that times out once rarely succeeds silently; failing fast surfaces the real state instead of a 30-minute silent retry loop.
- **LLM fan-out goes through `ordered_parallel_map` (`src/qalmsw/_concurrency.py`).** Grammar, math, and reviewer all take a `concurrency` ctor arg; the CLI exposes `--concurrency/-j`. Default is 1 (matches llama.cpp's default `--parallel 1`). Users bump both server and CLI together. Results are order-preserving so reports stay stable.
- **`.bib` parsing is hybrid**: a regex sweep over `@type{key,` headers owns keys + source line numbers (authoritative for MISSING / UNUSED / DUPLICATE), and `bibtexparser` pulls `title`/`author` fields by key. If bibtexparser fails or skips an entry, those fields fall back to empty strings — the entry is still present for citation checks. Don't let title/author extraction gate entry presence.
- **Bibliography discovery has two sources**: `.bib` files from `\bibliography{}` / `\addbibresource{}` (via `parse/citations.py::scan_bib_resources`), and inline `\begin{thebibliography}` blocks (via `bib/inline.py::extract_inline_bibitems`, which synthesizes `BibEntry` records from `\bibitem{key}` with a best-effort title guess). The CLI tries `.bib` first, falls back to inline, and emits an explicit warning only when both come up empty. Papers that ship pre-formatted bibliographies in the .tex body are a first-class case, not an error.

### Checker status

| Checker    | State      | Shape                                                       |
|------------|------------|-------------------------------------------------------------|
| `grammar`  | working    | Per-paragraph LLM call, parallelizable, cheap               |
| `math`     | working    | Per-paragraph math-formula consistency pass, parallelizable |
| `citations`| working    | Deterministic `.bib` vs `\cite` cross-check (MISSING / UNUSED / DUPLICATE). No LLM. |
| `reviewer` | working    | One LLM call per `\section{}` (or whole body if none); over-long sections are truncated |
| `claims`   | working, opt-in | Two LLM calls per paragraph-with-citation (extract, then judge per (claim, cite)). Scholar abstracts cached per bib key within a run. Opt in with `--enable-claims` — slow and rate-limited. |

When adding a checker: drop a file into `src/qalmsw/checkers/`, register it in `checkers/__init__.py`, wire it into `cli.py`'s `checkers` list, and add tests with a `FakeLLM` — don't hit the real server from tests.

### Citations module layout

- `src/qalmsw/bib/parser.py` — regex + `bibtexparser` hybrid over `@type{key,` headers and title/author fields.
- `src/qalmsw/bib/inline.py` — `\bibitem{}` extractor for inline `\begin{thebibliography}` blocks, returns `BibEntry` records.
- `src/qalmsw/parse/citations.py` — scanners for `\cite*` keys and `\bibliography{}` / `\addbibresource{}` paths.
- `src/qalmsw/checkers/citations.py` — the `CitationChecker`; receives parsed `BibEntry`s via its constructor so the CLI owns bibliography discovery and resolution.

### What's intentionally *not* here

- No LLM-assisted citation verification (does this citation actually support this claim?). That's the `claims` checker's territory.
- Retrieval uses **Semantic Scholar** by default (`src/qalmsw/retrieval/semantic_scholar.py`). Google Scholar remains available as an opt-in scraping backend and may hit rate limits or CAPTCHAs. Backend switching is done at runtime via `qalmsw.retrieval.set_backend()`.
- JSON report output exists in `report/json.py`; SARIF is still future work. The `Finding` pydantic model is the serialization seam for future output formats.
