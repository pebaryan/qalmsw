---
title: qalmsw
emoji: ✅
colorFrom: teal
colorTo: slate
sdk: gradio
sdk_version: 5.0.0
python_version: '3.11'
app_file: app.py
pinned: false
license: mit
short_description: automated QA for scientific LaTeX writing
---

# qalmsw

[![CI](https://github.com/pebaryan/qalmsw/actions/workflows/ci.yml/badge.svg)](https://github.com/pebaryan/qalmsw/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Local-first automated QA for scientific LaTeX writing, powered by a local LLM
through a llama.cpp OpenAI-compatible server.

qalmsw catches high-risk artifacts before submission: LLM meta-comments,
placeholder data, hallucinated references, missing figures, citation mistakes,
and claim/reference mismatches. Deterministic checks run without an LLM, while
grammar, math, reviewer, and claims checks are opt-in parts of a local review
workflow.

## Status

Pre-1.0 and actively maintained. The package has a Python CLI, focused tests,
JSON output for CI integrations, and a local-first architecture. See
[ROADMAP.md](ROADMAP.md) for the maintainer plan and Codex/API credit use case.

## What it catches

qalmsw checks for all three categories of "incontrovertible evidence" that arXiv's
Code of Conduct penalises:

| What arXiv flags | How qalmsw catches it |
|---|---|
| **LLM meta-comments** ("here is a 200-word summary", "would you like me to make any changes?") | `artifacts` checker - deterministic regex scan, no LLM needed |
| **Placeholder data** ("fill in with the real numbers", "this table is illustrative") | Same `artifacts` checker |
| **Hallucinated references** (bib entries for papers that don't exist) | `references` checker - verifies arXiv IDs and DOIs against live APIs |
| **Missing/placeholder captions** ("\caption{Insert caption here}") | `figures` checker - flags missing captions, placeholder text, orphan labels |
| **LLM self-awareness artifacts** ("as an AI language model", "I cannot provide") | `artifacts` checker |
| **LLM-generated LaTeX boilerplate** (\lipsum, \blindtext, TODO/FIXME) | `artifacts` checker |
| **Unreferenced figures/tables** | `figures` checker - warns on labels never \ref'd |
| **Missing image files** (\includegraphics pointing to non-existent files) | `images` checker - verifies referenced images exist on disk |
| **Grammar & style issues** | `grammar` checker - per-paragraph LLM pass |
| **Math formula consistency issues** | `math` checker - per-paragraph LLM pass |
| **Missing citations** | `citations` checker - cross-references \cite vs .bib |
| **Substantive reviewer concerns** | `reviewer` checker - per-section LLM critique |
| **Unsupported claims** *(opt-in)* | `claims` checker - checks each \cite-backed claim against the cited paper's abstract |

The first three rows are the highest-risk categories. qalmsw catches all of them
with deterministic checks, so they can run in CI without LLM cost.

## Quick start

```bash
pip install -e ".[dev]"

# Start llama.cpp server separately, e.g.
#   ./llama-server -m model.gguf -c 8192 --port 8080

qalmsw check path/to/paper.tex                             # run all checkers
qalmsw check --skip-grammar --skip-reviewer paper.tex      # deterministic checks only (fast)
qalmsw check --skip-math --skip-grammar --skip-reviewer paper.tex
qalmsw check --skip-grammar path/to/paper.tex              # reviewer + citations + artifacts + references
qalmsw check -j 4 path/to/paper.tex                        # fan out 4 parallel LLM calls
qalmsw check --bib refs.bib path/to/paper.tex              # override .bib auto-discovery
qalmsw check --json paper.tex                              # parseable JSON output for CI
qalmsw check ch1.tex ch2.tex ch3.tex                       # batch mode: check multiple files
qalmsw check "src/**/*.tex"                                # glob expansion

qalmsw scholar "Attention Is All You Need"                 # Semantic Scholar lookup (default, free API)
qalmsw check --enable-claims --retrieval google-scholar paper.tex  # claims check via Google Scholar
```

Environment variables:

- `QALMSW_BASE_URL` - llama.cpp server URL (default `http://localhost:8080/v1`)
- `QALMSW_MODEL` - model name (default `local-model`; llama.cpp usually ignores this)
- `QALMSW_API_KEY` - optional API key for non-local OpenAI-compatible endpoints

## Web frontend

The repository includes a Gradio frontend that can run as a Hugging Face Space.
Install the Space extra and start it locally with:

```bash
pip install -e ".[space]"
python app.py
```

For a hosted Space, the deterministic checks work without secrets. LLM-backed checks
can be configured from the web UI by entering:

- Base URL, such as `https://api.openai.com/v1`
- Model, using an ID supported by the selected backend
- API key, when the backend requires one

If those fields are left blank, the app falls back to `QALMSW_BASE_URL`,
`QALMSW_MODEL`, and `QALMSW_API_KEY` from Hugging Face Space variables/secrets.
For a public Space, prefer a Space secret for a shared API key; the web field is
best for user-supplied per-run credentials.

## Checkers

| Checker | LLM? | Speed | What it does |
|---|---|---|---|
| `artifacts` | No | Instant | Scans for LLM meta-comments, placeholders, self-awareness, boilerplate |
| `figures` | No | Instant | Checks captions, labels, refs, empty floats |
| `images` | No | Instant | Verifies \includegraphics files exist on disk |
| `citations` | No | Instant | `.bib` vs \cite cross-check: MISSING, UNUSED, DUPLICATE |
| `references` | Network | Slow | Verifies arXiv IDs and DOIs resolve to real papers |
| `grammar` | LLM | Per-paragraph | Grammar, spelling, punctuation |
| `math` | LLM | Per-paragraph | Formula notation and consistency |
| `reviewer` | LLM | Per-section | Motivation, clarity, argumentation, methodology |
| `claims` *(opt-in)* | LLM + Network | Very slow | For each \cite-backed claim, checks the abstract supports it |

Exit code is `1` only when an `error`-severity finding is present (missing citation,
LLM artifact, hallucinated reference), so unused-bib-entry `info`s or duplicate-key
`warning`s don't fail CI.

### Retrieval backends

The `claims` checker needs to fetch paper abstracts. Two backends are available:

| Backend | Flag | Auth | Reliability | Speed |
|---|---|---|---|---|
| **Semantic Scholar** (default) | `--retrieval semantic-scholar` | None | High (real API) | ~1 req/sec |
| **Google Scholar** | `--retrieval google-scholar` | None | Low (scraping, CAPTCHAs) | ~1 req/sec |

Default is Semantic Scholar - no auth, no CAPTCHAs, works in CI.

## arXiv Code of Conduct

arXiv's Code of Conduct (May 2026) states:

> "By signing your name as an author of a paper, each author takes full responsibility
> for all its contents, irrespective of how the contents were generated."

Penalties for incontrovertible evidence that authors didn't check LLM output:
**1-year ban**, followed by mandatory peer-reviewed venue acceptance.

Examples of incontrovertible evidence:
- Hallucinated references
- Meta-comments from the LLM
- Placeholder data in tables/figures

All three are caught by qalmsw's `artifacts`, `references`, and `figures` checkers -
which run deterministically with zero LLM cost.

## Architecture

The pipeline is **load → checkers → report**, and every checker produces a uniform
`Finding` so the report/CI layer never branches on checker type.

```
.tex file (+ .bib)
   │
   ▼
Document.load
   │  Document (path, source, paragraphs, line_map)
   ▼
checkers.*               # each implements check(doc) -> list[Finding]
   │
   ▼
report.render_findings   # rich-formatted terminal output (or --json for CI)
```

Deterministic checkers (artifacts, figures, images, citations) run first and always.
LLM checkers (grammar, math, reviewer, claims) run only when a server is available.
Network checkers (references, claims) make live API calls.

## Open Source

- License: [MIT](LICENSE)
- Contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Security policy: [SECURITY.md](SECURITY.md)
- Code of conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- Roadmap and funding plan: [ROADMAP.md](ROADMAP.md)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

