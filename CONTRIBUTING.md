# Contributing to qalmsw

qalmsw is a Python CLI for checking scientific LaTeX manuscripts before submission.
Contributions are welcome when they keep the tool reliable for local, privacy-preserving
review workflows.

## Development setup

```bash
pip install -e ".[dev]"
ruff check .
pytest -q
```

Tests use fake LLM clients and should not require a running llama.cpp server or live
network access. If a test needs paper metadata, stub the retrieval function.

## Project constraints

- The default LLM backend is a local llama.cpp server using an OpenAI-compatible API.
- Do not require hosted LLM providers for core checks.
- Deterministic checks should run before LLM-backed checks and should work in CI.
- Checkers should return `Finding` objects instead of printing directly.
- Do not ask the LLM for line numbers. Ask for excerpts and locate them in source.
- Keep output stable enough for CI and editor integrations.

## Adding a checker

1. Add the checker in `src/qalmsw/checkers/`.
2. Register it in `src/qalmsw/checkers/__init__.py`.
3. Wire it into `src/qalmsw/cli.py`.
4. Add focused tests under `tests/` with a fake LLM or stubbed retrieval backend.
5. Document the checker in `README.md`.

## Pull requests

Before opening a PR, run:

```bash
ruff check .
pytest -q
```

For user-visible behavior changes, include a short example command and explain the
expected report output.
