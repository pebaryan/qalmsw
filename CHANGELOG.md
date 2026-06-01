# Changelog

All notable project changes should be recorded here before a release is tagged.

## Unreleased

- Added CI configuration for linting and tests on supported Python versions.
- Added open-source project files: license, contributing guide, security policy,
  code of conduct, issue templates, and pull request template.
- Improved JSON output so CI consumers receive one parseable document for single
  or multi-file checks.
- Fixed claims-checker retrieval backend selection so runtime backend switches
  affect new `ClaimsChecker` instances.
- Added a Gradio web frontend for Hugging Face Spaces with configurable LLM backend fields.
