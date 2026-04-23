"""Base-corpus sampler — paragraphs-with-cite → (paragraph, cite_key, abstract) triples.

For each source paper we:
1. Inline ``\\input{}`` / ``\\include{}`` via qalmsw's resolver and split paragraphs.
2. Find paragraphs that contain at least one ``\\cite{}``.
3. Resolve each cite key to a cited-paper arXiv ID through the paper's bib file
   (matching by ``eprint``, ``archivePrefix``, or URL containing ``arxiv.org``).
4. Fetch the cited paper's abstract from the arXiv API (one network call per unique
   cite_key, cached).

The output is a ``BaseTriple`` per (paragraph, cite_key) pair with a non-empty
resolved abstract. The `identity` operator in ``defects.py`` assigns these the
default label ``supports`` — the core human-light assumption documented in PLAN.md.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from qalmsw.bib import BibEntry, extract_inline_bibitems, parse_bib_text
from qalmsw.parse import Paragraph, parse_paragraphs, scan_citations
from research.arxiv import SLEEP_BETWEEN_REQUESTS, ArxivMetadata, fetch_metadata

_ARXIV_ID_IN_FIELD_RE = re.compile(r"(\d{4}\.\d{4,5})(?:v\d+)?")
_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/([^\s},]+)")
_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")


@dataclass(frozen=True)
class BaseTriple:
    paper_id: str  # arXiv ID of the *citing* paper
    cite_key: str
    cited_arxiv_id: str
    paragraph_text: str
    paragraph_line: int  # 1-indexed line in the citing paper's source
    abstract: str
    cited_title: str


def _combined_source(tex_files: dict[str, str]) -> str:
    """Pick a main .tex file and return its content with ``\\input{}`` inlined.

    Heuristic for the main file: the one containing ``\\begin{document}``; tie-break
    on shortest path. Then recursively splice ``\\input{name}`` / ``\\include{name}``
    by looking up ``name``, ``name.tex``, and basename variants in ``tex_files``.
    Targets we can't resolve are left as the original ``\\input`` line — the cite
    scanner skips them without harm.

    This is a pure in-memory resolver; it does NOT touch the filesystem (we don't
    have the real directory layout when operating on an arXiv tarball).
    """
    candidates = [(name, text) for name, text in tex_files.items() if "\\begin{document}" in text]
    if not candidates:
        return ""
    candidates.sort(key=lambda nt: (len(nt[0]), nt[0]))
    main_name, main_text = candidates[0]
    return _inline_inputs(main_text, tex_files, stack=frozenset({main_name}))


def _resolve_input_name(name: str, tex_files: dict[str, str]) -> str | None:
    name = name.strip()
    for candidate in (name, f"{name}.tex"):
        if candidate in tex_files:
            return candidate
        # basename-only match (tarballs often have bare filenames).
        for key in tex_files:
            if key.endswith("/" + candidate) or key == candidate:
                return key
    return None


def _inline_inputs(text: str, tex_files: dict[str, str], stack: frozenset[str]) -> str:
    def _sub(m: re.Match[str]) -> str:
        resolved = _resolve_input_name(m.group(1), tex_files)
        if resolved is None or resolved in stack:
            return m.group(0)
        child_text = tex_files[resolved]
        return _inline_inputs(child_text, tex_files, stack | {resolved})

    return _INPUT_RE.sub(_sub, text)


def _extract_arxiv_id(bib_entry_text: str) -> str | None:
    """Pull an arXiv ID out of a raw bib entry body.

    Looks at common BibTeX conventions: ``eprint={1234.56789}``, ``url={...arxiv.org/abs/...}``,
    or any bare ``YYMM.NNNNN`` token.
    """
    m = _ARXIV_URL_RE.search(bib_entry_text)
    if m:
        cleaned = m.group(1).rstrip("}").rstrip(",").rstrip()
        mm = _ARXIV_ID_IN_FIELD_RE.search(cleaned)
        return mm.group(1) if mm else None
    m = _ARXIV_ID_IN_FIELD_RE.search(bib_entry_text)
    return m.group(1) if m else None


_ENTRY_BODY_WINDOW = 600


def _entry_window(haystack: str, entry_key: str) -> str:
    """Return up to ``_ENTRY_BODY_WINDOW`` chars following the key's first appearance.

    Matches both BibTeX (``@type{key,``) and inline-bibliography (``\\bibitem{key}``
    or ``\\bibitem[label]{key}``) conventions. We don't try to respect bracket
    nesting — a fixed window is simpler and sufficient to find an embedded arXiv ID.
    """
    for needle in (f"{{{entry_key},", f"{{{entry_key}}}"):
        idx = haystack.find(needle)
        if idx >= 0:
            start = idx + len(needle)
            return haystack[start : start + _ENTRY_BODY_WINDOW]
    return ""


def _resolve_cite_keys_to_arxiv(
    bib_entries: Iterable[BibEntry],
    haystack: str,
) -> dict[str, str]:
    """Return ``{cite_key: cited_arxiv_id}`` for every entry we can map."""
    mapping: dict[str, str] = {}
    for entry in bib_entries:
        window = _entry_window(haystack, entry.key)
        arxiv_id = _extract_arxiv_id(window)
        if arxiv_id:
            mapping[entry.key] = arxiv_id
    return mapping


def sample_triples_from_paper(
    paper_id: str,
    tex_files: dict[str, str],
    bib_text: str | None,
    *,
    max_per_paper: int = 5,
    fetch_meta: Callable[[str], ArxivMetadata | None] = fetch_metadata,
    sleep_between: float | None = None,
    abstract_cache: dict[str, ArxivMetadata | None] | None = None,
) -> list[BaseTriple]:
    """Produce base triples from one citing paper.

    ``bib_text`` is the concatenated text of the paper's .bib file(s). If the paper
    ships its bibliography inline (``\\begin{thebibliography}``), pass the .tex
    source as ``bib_text`` — ``extract_inline_bibitems`` is invoked regardless and
    both sources contribute to the key-to-arxiv-id map.

    At most ``max_per_paper`` triples are returned; sampling is deterministic
    (insertion order) so the caller can cap the corpus reproducibly.
    """
    source = _combined_source(tex_files)
    if not source:
        return []

    paragraphs = parse_paragraphs(source)
    bib_entries: list[BibEntry] = []
    effective_bib_text = bib_text if bib_text is not None else _collect_bib_text(tex_files)
    if effective_bib_text:
        bib_entries.extend(parse_bib_text(effective_bib_text, source=Path(f"{paper_id}.bib")))
    # Inline bibliography fallback — uses the .tex source itself, and also any .bbl
    # content appended into effective_bib_text.
    bib_entries.extend(extract_inline_bibitems(source, default_file=Path(f"{paper_id}.tex")))
    if effective_bib_text:
        bib_entries.extend(
            extract_inline_bibitems(effective_bib_text, default_file=Path(f"{paper_id}.bbl"))
        )
    if not bib_entries:
        return []

    haystack = (effective_bib_text or "") + "\n" + source
    key_to_arxiv = _resolve_cite_keys_to_arxiv(bib_entries, haystack)
    title_by_key = {e.key: e.title for e in bib_entries if e.title}

    effective_sleep = SLEEP_BETWEEN_REQUESTS if sleep_between is None else sleep_between
    cache = abstract_cache if abstract_cache is not None else {}
    triples: list[BaseTriple] = []
    for para in paragraphs:
        if len(triples) >= max_per_paper:
            break
        for cref in _unique_preserving_order(scan_citations(para.text)):
            if len(triples) >= max_per_paper:
                break
            arxiv_id = key_to_arxiv.get(cref.key)
            if not arxiv_id:
                continue
            if arxiv_id not in cache:
                cache[arxiv_id] = fetch_meta(arxiv_id)
                if effective_sleep:
                    time.sleep(effective_sleep)
            meta = cache[arxiv_id]
            if meta is None or not meta.abstract:
                continue
            triples.append(
                BaseTriple(
                    paper_id=paper_id,
                    cite_key=cref.key,
                    cited_arxiv_id=arxiv_id,
                    paragraph_text=para.text,
                    paragraph_line=para.start_line,
                    abstract=meta.abstract,
                    cited_title=title_by_key.get(cref.key) or meta.title,
                )
            )
    return triples


def _collect_bib_text(tex_files: dict[str, str]) -> str:
    """Concatenate every .bib and .bbl file in ``tex_files`` into one blob.

    Order: .bib first (BibTeX), then .bbl (rendered bibliography). ``bibtexparser``
    handles the BibTeX part; the inline-bibitem scanner handles the .bbl part.
    Missing bibliography is fine — the sampler just produces no triples.
    """
    pieces: list[str] = []
    for name, content in sorted(tex_files.items()):
        if name.lower().endswith(".bib"):
            pieces.append(content)
    for name, content in sorted(tex_files.items()):
        if name.lower().endswith(".bbl"):
            pieces.append(content)
    return "\n".join(pieces)


def _unique_preserving_order(refs):
    seen: set[str] = set()
    out = []
    for r in refs:
        if r.key in seen:
            continue
        seen.add(r.key)
        out.append(r)
    return out


def paragraph_has_cite(para: Paragraph) -> bool:
    return bool(scan_citations(para.text))
