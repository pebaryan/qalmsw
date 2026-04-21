# qalmsw

Automated QA for scientific LaTeX writing, powered by a local LLM (llama.cpp server).

## Status

Early scaffold. Grammar checker works end-to-end; citation, claim-to-reference, and reviewer-style checkers are planned.

## Quick start

```bash
pip install -e '.[dev]'

# Start llama.cpp server separately, e.g.
#   ./llama-server -m model.gguf -c 8192 --port 8080

qalmsw check path/to/paper.tex
```

Environment variables:

- `QALMSW_BASE_URL` — llama.cpp server URL (default `http://localhost:8080/v1`)
- `QALMSW_MODEL` — model name (default `local-model`; llama.cpp usually ignores this)

## Checkers

- `grammar` — per-paragraph grammar/style pass
- `citations` *(planned)* — `.bib` cross-check for missing/unused keys
- `claims` *(planned)* — claim-to-reference consistency via retrieval
- `reviewer` *(planned)* — whole-document reviewer-style critique
