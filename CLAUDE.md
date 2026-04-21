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

- **`Paragraph.start_line` / `end_line` are 1-indexed against the original source file** (not the stripped body). Findings point at these so editors can jump to the right line. Do not change this without updating every checker that constructs Findings.
- **Comment stripping preserves newlines** so line numbers stay stable after `%`-stripping. `parse.tex._COMMENT_RE` uses a negative look-behind to skip escaped `\%`.
- **Checkers receive a `Document`**, not just paragraphs. Citation-style checkers need the raw source (cites can appear outside prose paragraphs) and the path (to resolve `.bib` files). The `Checker` protocol is `check(doc: Document) -> list[Finding]`.
- **Non-prose paragraphs are filtered by the consumer**, not at load time. `GrammarChecker` calls `has_prose()` per paragraph so citation-scanning checkers still see headings. Don't pre-filter in the CLI.
- **CLI exit code is `1` only when an `error`-severity finding exists.** `info` (unused bib entry) and `warning` (duplicate bib key) findings are non-fatal by design — drafts routinely have them.
- **`LLMClient` is a `typing.Protocol`**, not an ABC. Tests pass a `FakeLLM` that only implements `complete_json`. Don't tighten the interface into a base class; the Protocol is intentional so any object with the right shape works.
- **Checkers never ask the LLM for line numbers.** Small local models count lines unreliably. Instead they ask for an `excerpt` string and we locate it in the paragraph text (`grammar._locate_line`). New checkers should follow this pattern.
- **Structured output uses `response_format={"type": "json_object"}`** — supported by llama.cpp server. The system prompt must also spell out the JSON shape, because small models otherwise drift.
- **`LLMClient` has `max_retries=0`.** A slow local model that times out once rarely succeeds silently; failing fast surfaces the real state instead of a 30-minute silent retry loop.
- **LLM fan-out goes through `ordered_parallel_map` (`src/qalmsw/_concurrency.py`).** Grammar and reviewer both take a `concurrency` ctor arg; the CLI exposes `--concurrency/-j`. Default is 1 (matches llama.cpp's default `--parallel 1`). Users bump both server and CLI together. Results are order-preserving so reports stay stable.
- **`.bib` parsing is regex-based**, not a full BibTeX parser. We extract `@type{key,` headers + line numbers because that's all MISSING / UNUSED / DUPLICATE needs. If we ever need field values, swap in `bibtexparser`; don't grow the regex.

### Checker status

| Checker    | State      | Shape                                                       |
|------------|------------|-------------------------------------------------------------|
| `grammar`  | working    | Per-paragraph LLM call, parallelizable, cheap               |
| `citations`| working    | Deterministic `.bib` vs `\cite` cross-check (MISSING / UNUSED / DUPLICATE). No LLM. |
| `reviewer` | working    | One LLM call per `\section{}` (or whole body if none); over-long sections are truncated |
| `claims`   | **planned**| Needs retrieval (arXiv / local PDF cache / S2) + LLM judge — most expensive |

When adding a checker: drop a file into `src/qalmsw/checkers/`, register it in `checkers/__init__.py`, wire it into `cli.py`'s `checkers` list, and add tests with a `FakeLLM` — don't hit the real server from tests.

### Citations module layout

- `src/qalmsw/bib/parser.py` — regex extractor over `@type{key,` headers + source lines.
- `src/qalmsw/parse/citations.py` — scanners for `\cite*` keys and `\bibliography{}` / `\addbibresource{}` paths.
- `src/qalmsw/checkers/citations.py` — the `CitationChecker`; receives parsed `BibEntry`s via its constructor so the CLI owns `.bib` discovery and resolution.

### What's intentionally *not* here

- No multi-file `\input{}` / `\include{}` resolution yet — single-file only.
- No LLM-assisted citation verification (does this citation actually support this claim?). That's the `claims` checker's territory.
- No retrieval layer yet — will live in `src/qalmsw/retrieval/` when the claims checker lands.
- No SARIF/JSON report formats yet — only `report/text.py`. The `Finding` pydantic model is the serialization seam when those arrive.
