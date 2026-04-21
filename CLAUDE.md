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

The pipeline is **parse → checkers → report**, and every checker produces a uniform `Finding` so the report/CI layer never branches on checker type.

```
.tex file
   │
   ▼
parse.parse_paragraphs         # blank-line-split, comments stripped,
   │  list[Paragraph]           # source line numbers preserved
   ▼
checkers.*                     # each implements the Checker protocol:
   │  list[Finding]            #     check(paragraphs) -> list[Finding]
   ▼
report.render_findings         # rich-formatted terminal output
```

### Contracts worth preserving

- **`Paragraph.start_line` / `end_line` are 1-indexed against the original source file** (not the stripped body). Findings point at these so editors can jump to the right line. Do not change this without updating every checker that constructs Findings.
- **Comment stripping preserves newlines** so line numbers stay stable after `%`-stripping. `parse.tex._COMMENT_RE` uses a negative look-behind to skip escaped `\%`.
- **`LLMClient` is a `typing.Protocol`**, not an ABC. Tests pass a `FakeLLM` that only implements `complete_json`. Don't tighten the interface into a base class; the Protocol is intentional so any object with the right shape works.
- **Checkers never ask the LLM for line numbers.** Small local models count lines unreliably. Instead they ask for an `excerpt` string and we locate it in the paragraph text (`grammar._locate_line`). New checkers should follow this pattern.
- **Structured output uses `response_format={"type": "json_object"}`** — supported by llama.cpp server. The system prompt must also spell out the JSON shape, because small models otherwise drift.

### Checker status

| Checker    | State      | Shape                                                       |
|------------|------------|-------------------------------------------------------------|
| `grammar`  | working    | Per-paragraph LLM call, parallelizable, cheap               |
| `citations`| **planned**| Mostly deterministic `.bib` vs `\cite` cross-check, LLM only to verify a cited work actually supports the claim |
| `claims`   | **planned**| Needs retrieval (arXiv / local PDF cache / S2) + LLM judge — most expensive |
| `reviewer` | **planned**| Whole-document pass, must chunk to fit local-model context  |

When adding a checker: drop a file into `src/qalmsw/checkers/`, register it in `checkers/__init__.py`, wire it into `cli.py`'s `checkers` list, and add tests with a `FakeLLM` — don't hit the real server from tests.

### What's intentionally *not* here

- No multi-file `\input{}` / `\include{}` resolution yet — single-file only.
- No `.bib` parser yet — will live in `src/qalmsw/bib/` when the citation checker lands.
- No retrieval layer yet — will live in `src/qalmsw/retrieval/` when the claims checker lands.
- No SARIF/JSON report formats yet — only `report/text.py`. The `Finding` pydantic model is the serialization seam when those arrive.
