# Changelog

All notable project changes should be recorded here before a release is tagged.

## Unreleased

- The `references` checker can delegate to LitKG (`pip install qalmsw[litkg]`): title,
  author, and year comparison against registry records, title search for entries without
  an identifier, suggested corrections, and LitKG library papers as evidence. New options
  `--references-backend`, `--library`, and `--mailto`; the built-in check remains the
  fallback.
- Added CI configuration for linting and tests on supported Python versions.
- Added open-source project files: license, contributing guide, security policy,
  code of conduct, issue templates, and pull request template.
- Improved JSON output so CI consumers receive one parseable document for single
  or multi-file checks.
- Fixed claims-checker retrieval backend selection so runtime backend switches
  affect new `ClaimsChecker` instances.
- Added a Gradio web frontend for Hugging Face Spaces with configurable LLM backend fields.
- Added `--skip-references` and checker progress messages so slow network
  reference validation can be bypassed or identified.
