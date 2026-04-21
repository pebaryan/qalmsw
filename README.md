# qalmsw

Automated QA for scientific LaTeX writing, powered by a local LLM (llama.cpp server).

## Status

Grammar and citation checkers work end-to-end. Claim-to-reference and reviewer-style checkers are planned.

## Quick start

```bash
pip install -e '.[dev]'

# Start llama.cpp server separately, e.g.
#   ./llama-server -m model.gguf -c 8192 --port 8080

qalmsw check path/to/paper.tex                     # run all checkers
qalmsw check --skip-grammar path/to/paper.tex      # deterministic citation checks only
qalmsw check --bib refs.bib path/to/paper.tex      # override .bib auto-discovery
```

Environment variables:

- `QALMSW_BASE_URL` — llama.cpp server URL (default `http://localhost:8080/v1`)
- `QALMSW_MODEL` — model name (default `local-model`; llama.cpp usually ignores this)

## Checkers

- `grammar` — per-paragraph grammar/style pass (LLM-backed)
- `citations` — `.bib` vs `\cite` cross-check: MISSING keys, UNUSED entries, DUPLICATE keys
- `claims` *(planned)* — claim-to-reference consistency via retrieval
- `reviewer` *(planned)* — whole-document reviewer-style critique

Exit code is `1` only when an `error`-severity finding is present (missing citation, grammar error), so drafts with unused-bib-entry `info`s or duplicate-key `warning`s don't fail CI.
