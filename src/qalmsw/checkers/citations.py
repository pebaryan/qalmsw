"""Citation consistency checker.

Cross-references the ``\\cite{}`` keys found in the document against the parsed
``.bib`` entries and emits three kinds of findings:

* **MISSING** — a cited key has no matching bib entry. Error; blocks a clean build.
* **UNUSED** — a bib entry that no ``\\cite`` references. Info; drafts routinely carry
  these and the user can choose to prune.
* **DUPLICATE** — the same key is defined by multiple bib entries. Warning; BibTeX will
  silently use one and drop the rest.

Bib entries are passed in at construction time because discovering and parsing ``.bib``
files is the CLI's responsibility (it knows the document's directory and can resolve
relative paths correctly).
"""
from __future__ import annotations

from qalmsw.bib import BibEntry
from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document
from qalmsw.parse import scan_citations


class CitationChecker:
    name = "citations"

    def __init__(self, bib_entries: list[BibEntry]) -> None:
        self._bib_entries = bib_entries

    def check(self, doc: Document) -> list[Finding]:
        citations = scan_citations(doc.source)
        cited_keys = {c.key for c in citations}

        entries_by_key: dict[str, list[BibEntry]] = {}
        for entry in self._bib_entries:
            entries_by_key.setdefault(entry.key, []).append(entry)
        known_keys = set(entries_by_key)

        findings: list[Finding] = []

        for cite in citations:
            if cite.key not in known_keys:
                findings.append(
                    Finding(
                        checker=self.name,
                        severity=Severity.error,
                        line=cite.line,
                        message=f"Cited key '{cite.key}' not found in bibliography.",
                        excerpt=f"\\cite{{{cite.key}}}",
                    )
                )

        for key, entries in entries_by_key.items():
            if key not in cited_keys:
                first = entries[0]
                findings.append(
                    Finding(
                        checker=self.name,
                        severity=Severity.info,
                        file=str(first.file),
                        line=first.line,
                        message=f"Unused bibliography entry '{key}'.",
                    )
                )
            if len(entries) > 1:
                primary = entries[0]
                for dup in entries[1:]:
                    findings.append(
                        Finding(
                            checker=self.name,
                            severity=Severity.warning,
                            file=str(dup.file),
                            line=dup.line,
                            message=(
                                f"Duplicate bibliography key '{key}' "
                                f"(first defined at {primary.file}:{primary.line})."
                            ),
                        )
                    )

        return findings
