"""arXiv fetchers for corpus construction.

We need two things per paper:

- The ``.tex`` source (so qalmsw's parsers can extract paragraphs and cites).
- The abstract of each cited paper (so we can pair "claim" with "cited abstract").

Both are served by ``export.arxiv.org`` — abstracts via the Atom query API, source via
the ``e-print`` endpoint which returns a gzipped tarball. Stdlib only: no new deps just
for network + XML.

Rate-limit note: arXiv asks for <=1 request per 3 seconds. The module exposes a
cooperative ``SLEEP_BETWEEN_REQUESTS`` knob; callers driving bulk fetches should leave
it at the default. Tests stub the HTTP layer and set it to 0.
"""
from __future__ import annotations

import gzip
import io
import re
import tarfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

SLEEP_BETWEEN_REQUESTS: float = 3.0

_QUERY_URL = "https://export.arxiv.org/api/query"
_EPRINT_URL = "https://export.arxiv.org/e-print/"
_USER_AGENT = "qalmsw-research/0.1 (mailto:pebaryan@outlook.com)"

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class ArxivMetadata:
    arxiv_id: str
    title: str
    abstract: str


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 — fixed-scheme URL
        return resp.read()


def fetch_metadata(arxiv_id: str) -> ArxivMetadata | None:
    """Return title + abstract for ``arxiv_id``, or None if the paper is unknown.

    ``arxiv_id`` may include a version suffix (``2301.12345v2``) — arXiv strips it.
    """
    params = urllib.parse.urlencode({"id_list": arxiv_id})
    raw = _http_get(f"{_QUERY_URL}?{params}")
    root = ET.fromstring(raw)
    entry = root.find("a:entry", _ATOM_NS)
    if entry is None:
        return None
    title_el = entry.find("a:title", _ATOM_NS)
    summary_el = entry.find("a:summary", _ATOM_NS)
    if title_el is None or summary_el is None:
        return None
    # arXiv's Atom feed uses a placeholder entry for missing IDs.
    id_el = entry.find("a:id", _ATOM_NS)
    if id_el is not None and "api/errors" in (id_el.text or ""):
        return None
    return ArxivMetadata(
        arxiv_id=arxiv_id,
        title=_normalize(title_el.text or ""),
        abstract=_normalize(summary_el.text or ""),
    )


_TEXTUAL_EXTS = (".tex", ".bbl", ".bib")


def fetch_source(arxiv_id: str) -> dict[str, str]:
    """Return ``{filename: content}`` for every .tex / .bbl / .bib file in the paper's tarball.

    arXiv's e-print endpoint returns either a gzipped single-file .tex or a
    gzipped tarball; we handle both. Non-textual files (.pdf, images, .sty, etc.)
    are dropped. Returns an empty dict if no textual files are present (e.g.
    PDF-only submissions).
    """
    raw = _http_get(f"{_EPRINT_URL}{arxiv_id}")
    return _extract_tex_files(raw)


def fetch_both(arxiv_id: str) -> tuple[ArxivMetadata | None, dict[str, str]]:
    """Convenience: fetch metadata + source with rate-limit sleep between calls."""
    meta = fetch_metadata(arxiv_id)
    if SLEEP_BETWEEN_REQUESTS:
        time.sleep(SLEEP_BETWEEN_REQUESTS)
    source = fetch_source(arxiv_id)
    return meta, source


def _extract_tex_files(raw: bytes) -> dict[str, str]:
    # Try tarball first.
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:*") as tar:
            files: dict[str, str] = {}
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                lower = member.name.lower()
                if not lower.endswith(_TEXTUAL_EXTS):
                    continue
                buf = tar.extractfile(member)
                if buf is None:
                    continue
                try:
                    files[member.name] = buf.read().decode("utf-8", errors="replace")
                except Exception:
                    continue
            if files:
                return files
    except tarfile.TarError:
        pass
    # Fall back to single gzipped .tex.
    try:
        decompressed = gzip.decompress(raw)
    except OSError:
        decompressed = raw
    text = decompressed.decode("utf-8", errors="replace")
    if "\\documentclass" in text or "\\begin{document}" in text:
        return {"main.tex": text}
    return {}


_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()
