"""Reference Validation Checker.

Verifies that bibliography entries correspond to real papers by:
- Checking arXiv eprint IDs against the arXiv API
- Resolving DOIs against doi.org
- Noting entries that can't be verified (no eprint or DOI)

This catches hallucinated references — bib entries that look plausible but
reference papers that don't exist (a common LLM artifact and one of arXiv's
"incontrovertible evidence" categories for a 1-year ban).

Design:
- Uses stdlib urllib only (no external dependencies)
- Results are cached per-run by bib key
- arXiv API: https://export.arxiv.org/api/query?id_list=
- DOI: HEAD https://doi.org/DOI (checks HTTP 200)
- Failures are non-fatal (info findings); confirmed hallucinations are errors

When LitKG (https://github.com/pebaryan/litkg) is installed, the checker can delegate to
its reference backend instead (see ``litkg_backend``). LitKG also compares each entry's
title, authors, and year with the registry record, finds entries without an identifier
by title search, suggests the correct record, and counts papers in a LitKG library as
verified.
"""

from __future__ import annotations

import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qalmsw.bib import BibEntry
from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document

_ARXIV_API = "https://export.arxiv.org/api/query?id_list={}"
_DOI_RESOLVER = "https://doi.org/{}"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}

# Rate limiting: arXiv asks for no more than 1 request per 3 seconds.
_ARXIV_DELAY = 3.1  # seconds between arXiv API calls

# Regex to extract arXiv ID from various forms
_ARXIV_ID_RE = re.compile(
    r"(?:arxiv|arXiv)?[.:/\s]*"
    r"(?:\d{4}\.\d{4,5}(?:v\d+)?)"
)

_EPRINT_ID_RE = re.compile(
    r"(?:\d{4}\.\d{4,5})(?:v\d+)?"
)


def _extract_arxiv_id(raw: str) -> str | None:
    """Extract a clean arXiv ID from an eprint field value."""
    m = _EPRINT_ID_RE.search(raw)
    return m.group(0) if m else None


def _verify_arxiv(arxiv_id: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Check if an arXiv paper exists. Returns (exists, title_or_error)."""
    url = _ARXIV_API.format(arxiv_id)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qalmsw/0.0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml_data = resp.read().decode("utf-8")
        root = ET.fromstring(xml_data)
        entries = root.findall("atom:entry", _ARXIV_NS)
        if not entries:
            return False, "No entry returned by arXiv API"
        title_el = entries[0].find("atom:title", _ARXIV_NS)
        title = title_el.text.strip() if title_el is not None else "(no title)"
        return True, title
    except (urllib.error.HTTPError, urllib.error.URLError, ET.ParseError, OSError) as e:
        return False, str(e)


def _verify_doi(doi: str, timeout: float = 10.0) -> tuple[bool, str]:
    """Check if a DOI resolves. Returns (exists, resolved_url_or_error)."""
    url = _DOI_RESOLVER.format(doi)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qalmsw/0.0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # doi.org redirects to the publisher's page
            return True, resp.url
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        return False, str(e)


VerifyFn = Callable[[BibEntry], tuple[bool, str] | None]

_LITKG_SEVERITY = {"error": Severity.error, "warning": Severity.warning, "note": Severity.info}
_LITKG_BIB_SUFFIXES = frozenset({".bib", ".json"})
# Nothing actionable: web/@misc entries and entries without a title are not looked up.
_LITKG_SILENT = frozenset({"not-indexed", "no-title"})


def litkg_backend(
    store: str | Path | None = None,
    mailto: str | None = None,
    cache_dir: str | Path | None = ".litkg_cache",
) -> Any | None:
    """Return a LitKG reference backend, or ``None`` when LitKG is not installed."""
    try:
        from litkg.api import ReferenceBackend
    except ImportError:
        return None
    return ReferenceBackend(online=True, store=store, mailto=mailto, cache_dir=cache_dir)


def _format_candidate(record: Any) -> str:
    authors = list(record.authors or [])
    names = "; ".join(authors[:3]) + (" et al." if len(authors) > 3 else "")
    parts = [f'"{record.title}"'] if record.title else []
    if names:
        parts.append(names)
    if record.year:
        parts.append(f"({record.year})")
    if record.doi:
        parts.append(f"doi:{record.doi}")
    elif record.arxiv_id:
        parts.append(f"arXiv:{record.arxiv_id}")
    return " ".join(parts)


class ReferenceChecker:
    """Verifies bibliography entries against external APIs.

    Runs after citation consistency checks — this is a deeper (and slower)
    verification that actually checks if referenced papers exist.

    The default verifier checks arXiv eprint IDs and DOIs. Override via
    constructor for tests.
    """

    name = "references"

    def __init__(
        self,
        bib_entries: list[BibEntry],
        verify: VerifyFn | None = None,
        backend: Any | None = None,
    ) -> None:
        self._bib_entries = bib_entries
        self._verify = verify or self._default_verify
        self._backend = None if verify is not None else backend
        self._cache: dict[str, tuple[bool, str] | None] = {}
        self._last_arxiv_call = 0.0

    def check(self, doc: Document) -> list[Finding]:
        if self._backend is not None:
            return self._check_with_litkg()
        findings: list[Finding] = []
        for entry in self._bib_entries:
            result = self._check_entry(entry)
            if result is not None:
                findings.append(result)
        return findings

    def _check_with_litkg(self) -> list[Finding]:
        from litkg.api import make_entry

        unique: dict[str, BibEntry] = {}
        for entry in self._bib_entries:
            unique.setdefault(entry.key, entry)

        # LitKG's own parser keeps the fields it compares (year, full author list, @string
        # macros); qalmsw's fields are the fallback for inline ibitem entries.
        parsed: dict[Path, dict[str, Any]] = {}
        infos = []
        for entry in unique.values():
            info = None
            path = Path(entry.file) if entry.file else None
            if path and path.suffix.lower() in _LITKG_BIB_SUFFIXES and path.is_file():
                if path not in parsed:
                    try:
                        loaded = self._backend.load_bibliography(path)
                    except (OSError, ValueError):
                        loaded = []
                    parsed[path] = {item.key: item for item in loaded if item.key}
                info = parsed[path].get(entry.key)
            if info is None:
                info = make_entry(
                    key=entry.key,
                    title=entry.title,
                    authors=entry.author,
                    doi=entry.doi,
                    eprint=entry.eprint,
                    entry_type=entry.entry_type,
                )
            infos.append(info)

        try:
            verdicts = self._backend.verify(infos)
        finally:
            self._backend.close()

        findings: list[Finding] = []
        for entry, verdict in zip(unique.values(), verdicts, strict=True):
            suggested = False
            for item in verdict.findings:
                if item.code in _LITKG_SILENT:
                    continue
                suggestion = None
                if verdict.candidate is not None and not suggested and item.severity != "note":
                    candidate = _format_candidate(verdict.candidate)
                    suggestion = f"Possible correct reference: {candidate}"
                    suggested = True
                findings.append(
                    Finding(
                        checker=self.name,
                        severity=_LITKG_SEVERITY.get(item.severity, Severity.info),
                        file=str(entry.file),
                        line=entry.line,
                        message=f"Reference '{entry.key}' ({item.code}): {item.message}",
                        suggestion=suggestion,
                    )
                )
        return findings

    def _check_entry(self, entry: BibEntry) -> Finding | None:
        if entry.key in self._cache:
            result = self._cache[entry.key]
        else:
            result = self._verify(entry)
            self._cache[entry.key] = result

        if result is None:
            return None
        exists, detail = result
        if exists:
            return None  # All good — silent

        # Determine severity based on what we tried
        has_eprint = bool(entry.eprint and entry.eprint.strip())
        has_doi = bool(entry.doi and entry.doi.strip())

        if has_eprint:
            return Finding(
                checker=self.name,
                severity=Severity.error,
                file=str(entry.file),
                line=entry.line,
                message=(
                    f"Reference '{entry.key}' has arXiv ID {entry.eprint!r} "
                    f"but arXiv returned no result: {detail}"
                ),
                suggestion=(
                    "This paper may not exist — verify the arXiv ID manually. "
                    "If the reference is hallucinated, remove or replace it."
                ),
            )
        elif has_doi:
            return Finding(
                checker=self.name,
                severity=Severity.error,
                file=str(entry.file),
                line=entry.line,
                message=(
                    f"Reference '{entry.key}' has DOI {entry.doi!r} "
                    f"but doi.org returned no result: {detail}"
                ),
                suggestion="This paper may not exist — verify the DOI manually.",
            )
        else:
            return Finding(
                checker=self.name,
                severity=Severity.info,
                file=str(entry.file),
                line=entry.line,
                message=(
                    f"Reference '{entry.key}' cannot be verified: "
                    f"no arXiv ID or DOI in the bib entry."
                ),
                suggestion=(
                    "Add an eprint or DOI field to the .bib entry for automatic verification. "
                    "This helps guard against hallucinated references."
                ),
            )

    def _default_verify(self, entry: BibEntry) -> tuple[bool, str] | None:
        """Default verification: arXiv ID > DOI > nothing."""
        eprint_raw = (entry.eprint or "").strip()
        doi_raw = (entry.doi or "").strip()

        if eprint_raw:
            arxiv_id = _extract_arxiv_id(eprint_raw)
            if arxiv_id:
                # Rate limit arXiv API
                now = time.time()
                since_last = now - self._last_arxiv_call
                if since_last < _ARXIV_DELAY:
                    time.sleep(_ARXIV_DELAY - since_last)
                self._last_arxiv_call = time.time()
                return _verify_arxiv(arxiv_id)

        if doi_raw:
            return _verify_doi(doi_raw)

        return None
