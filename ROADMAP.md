# Roadmap

qalmsw is focused on pre-submission QA for scientific LaTeX manuscripts. The
near-term goal is to make the deterministic checks strong enough for CI, and the
LLM-backed checks useful enough for private local review before authors submit.

## Current priorities

- Keep deterministic artifact, citation, image, and figure/table checks fast and
  suitable for CI.
- Improve JSON output and add SARIF output so editors, GitHub Actions, and review
  tools can annotate exact manuscript lines.
- Expand reference verification beyond arXiv and DOI checks with better fallbacks
  for Semantic Scholar, Crossref, and OpenAlex.
- Build a small public regression corpus of synthetic LaTeX manuscripts that cover
  hallucinated references, placeholder content, missing figures, and unsupported
  claims.
- Publish reproducible releases with changelogs and pinned test results.

## Codex/API Credit Plan

OpenAI's Codex open source programs ask how API credits would support project work.
For qalmsw, credits would be used for bounded maintainer automation and evaluation,
not for sending users' manuscripts to hosted services by default.

Planned uses:

- Generate and review checker test cases from synthetic LaTeX fixtures.
- Compare checker output across models and prompts before releases.
- Prototype SARIF/GitHub Actions annotations for manuscript review workflows.
- Triage issues and draft pull-request reviews for community contributions.
- Build release notes and migration notes from merged changes.

User-facing checks should continue to support local llama.cpp by default. Hosted API
usage belongs in maintainer workflows, opt-in experiments, or clearly documented
integrations.

## Funding Application Draft

Short project description:

> qalmsw is an open-source Python CLI that checks scientific LaTeX manuscripts for
> LLM artifacts, placeholder text, hallucinated references, missing figures, citation
> problems, and unsupported claims before submission.

How credits would be used:

> API credits would fund maintainer automation: synthetic LaTeX regression fixtures,
> checker evaluation, issue/PR triage, release-note drafting, and CI annotation
> prototypes. The user CLI remains local-first with llama.cpp; hosted API use is for
> project maintenance and opt-in integrations.
