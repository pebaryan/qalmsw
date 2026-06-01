# Security Policy

## Supported versions

qalmsw is pre-1.0. Security fixes are applied to the `main` branch until formal
releases are published.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability.

Report security-sensitive problems by emailing the maintainer listed on the GitHub
repository profile, or by opening a private GitHub security advisory if that is
enabled for the repository.

Useful details include:

- A minimal input file or command that triggers the issue.
- Whether the issue requires network retrieval or an LLM server.
- Any file paths, URLs, or environment variables involved.

## Security model

qalmsw reads LaTeX and BibTeX files supplied by the user and may call local LLM and
metadata retrieval services. It should not execute LaTeX, shell commands from input,
or arbitrary code embedded in a manuscript.

The default LLM endpoint is a local llama.cpp server. Users who configure another
OpenAI-compatible endpoint are responsible for that provider's data handling terms.
