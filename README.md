# qalmsw

Automated QA for scientific LaTeX writing, powered by a local LLM (llama.cpp server).
Catches the artefacts that get you a 1-year arXiv ban — before you submit.

## What it catches

qalmsw now checks for all three categories of "incontrovertible evidence" that arXiv's
Code of Conduct penalises:

| What arXiv flags | How qalmsw catches it |
|---|---|
| **LLM meta-comments** ("here is a 200-word summary", "would you like me to make any changes?") | `artifacts` checker — deterministic regex scan, no LLM needed |
| **Placeholder data** ("fill in with the real numbers", "this table is illustrative") | Same `artifacts` checker |
| **Hallucinated references** (bib entries for papers that don't exist) | `references` checker — verifies arXiv IDs and DOIs against live APIs |
| **Missing/placeholder captions** ("\caption{Insert caption here}") | `figures` checker — flags missing captions, placeholder text, orphan labels |
| **LLM self-awareness artifacts** ("as an AI language model", "I cannot provide") | `artifacts` checker |
| **LLM-generated LaTeX boilerplate** (\lipsum, \blindtext, TODO/FIXME) | `artifacts` checker |
| **Unreferenced figures/tables** | `figures` checker — warns on labels never \ref'd |
| **Grammar & style issues** | `grammar` checker — per-paragraph LLM pass |
| **Missing citations** | `citations` checker — cross-references \cite vs .bib |
| **Substantive reviewer concerns** | `reviewer` checker — per-section LLM critique |

The first three rows are the ones that get you banned. qalmsw catches all of them.

## Quick start

```bash
pip install -e '.[dev]'

# Start llama.cpp server separately, e.g.
#   ./llama-server -m model.gguf -c 8192 --port 8080

qalmsw check path/to/paper.tex                             # run all checkers
qalmsw check --skip-grammar --skip-reviewer paper.tex      # deterministic checks only (fast)
qalmsw check --skip-grammar path/to/paper.tex              # reviewer + citations + artifacts + references
qalmsw check -j 4 path/to/paper.tex                        # fan out 4 parallel LLM calls (match server --parallel N)
qalmsw check --bib refs.bib path/to/paper.tex              # override .bib auto-discovery

qalmsw scholar "Attention Is All You Need"                 # Google Scholar lookup (scraping; expect CAPTCHAs on bulk use)
```

Environment variables:

- `QALMSW_BASE_URL` — llama.cpp server URL (default `http://localhost:8080/v1`)
- `QALMSW_MODEL` — model name (default `local-model`; llama.cpp usually ignores this)

## Checkers

| Checker | LLM? | Speed | What it does |
|---|---|---|---|
| `artifacts` | No | Instant | Scans for LLM meta-comments, placeholders, self-awareness, boilerplate |
| `figures` | No | Instant | Checks captions, labels, refs, empty floats |
| `citations` | No | Instant | `.bib` vs `\cite` cross-check: MISSING, UNUSED, DUPLICATE |
| `references` | Network | Slow | Verifies arXiv IDs and DOIs resolve to real papers |
| `grammar` | LLM | Per-paragraph | Grammar, spelling, punctuation |
| `reviewer` | LLM | Per-section | Motivation, clarity, argumentation, methodology |
| `claims` *(opt-in)* | LLM + Network | Very slow | For each \cite-backed claim, checks the abstract supports it |

Exit code is `1` only when an `error`-severity finding is present (missing citation,
LLM artifact, hallucinated reference), so unused-bib-entry `info`s or duplicate-key
`warning`s don't fail CI.

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

All three are caught by qalmsw's `artifacts`, `references`, and `figures` checkers —
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
report.render_findings   # rich-formatted terminal output
```

Deterministic checkers (artifacts, figures, citations) run first and always.
LLM checkers (grammar, reviewer, claims) run only when a server is available.
