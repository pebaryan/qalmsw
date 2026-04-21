# qalmsw

Automated QA for scientific LaTeX writing, powered by a local LLM (llama.cpp server).

## Status

Grammar, citation, and reviewer checkers work end-to-end. Claim-to-reference is planned.

## Quick start

```bash
pip install -e '.[dev]'

# Start llama.cpp server separately, e.g.
#   ./llama-server -m model.gguf -c 8192 --port 8080

qalmsw check path/to/paper.tex                             # run all checkers
qalmsw check --skip-grammar --skip-reviewer paper.tex      # deterministic citation checks only
qalmsw check --skip-grammar path/to/paper.tex              # reviewer + citations, no per-paragraph grammar
qalmsw check -j 4 path/to/paper.tex                        # fan out 4 parallel LLM calls (match server --parallel N)
qalmsw check --bib refs.bib path/to/paper.tex              # override .bib auto-discovery

qalmsw scholar "Attention Is All You Need"                 # Google Scholar lookup (scraping; expect CAPTCHAs on bulk use)
```

Environment variables:

- `QALMSW_BASE_URL` — llama.cpp server URL (default `http://localhost:8080/v1`)
- `QALMSW_MODEL` — model name (default `local-model`; llama.cpp usually ignores this)

## Checkers

- `grammar` — per-paragraph grammar/style pass (LLM-backed)
- `citations` — `.bib` vs `\cite` cross-check: MISSING keys, UNUSED entries, DUPLICATE keys
- `reviewer` — one LLM critique per `\section{}`, focused on motivation / clarity / argumentation / methodology / evaluation / structure
- `claims` *(planned)* — claim-to-reference consistency via retrieval

Exit code is `1` only when an `error`-severity finding is present (missing citation, grammar error), so drafts with unused-bib-entry `info`s or duplicate-key `warning`s don't fail CI.
