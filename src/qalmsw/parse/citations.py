"""Scan a .tex source for citation keys and bibliography resource declarations.

Works directly on the raw source (after comment stripping) because citations can appear
anywhere — not only inside prose paragraphs — and we need file-accurate line numbers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from qalmsw.parse.tex import _COMMENT_RE

# Matches natbib + biblatex cite commands: \cite, \citep, \citet, \citeauthor,
# \citeyear, \nocite, \parencite, \textcite, \autocite, \footcite (+ star variants,
# optional pre/post-note brackets).
_CITE_RE = re.compile(
    r"\\(?:no|paren|text|auto|foot)?cite[a-zA-Z]*\*?"
    r"(?:\[[^\]]*\])*"
    r"\{([^}]+)\}"
)

# \bibliography{a,b}  (bibtex)   and   \addbibresource{a.bib}  (biblatex)
_BIBLIOGRAPHY_RE = re.compile(r"\\bibliography\{([^}]+)\}")
_ADDBIBRESOURCE_RE = re.compile(r"\\addbibresource\{([^}]+)\}")


@dataclass(frozen=True)
class CitationRef:
    key: str
    line: int


def scan_citations(source: str) -> list[CitationRef]:
    """Return every cited key with its 1-indexed source line."""
    text = _COMMENT_RE.sub("", source)
    refs: list[CitationRef] = []
    for match in _CITE_RE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        for raw_key in match.group(1).split(","):
            key = raw_key.strip()
            if key:
                refs.append(CitationRef(key=key, line=line))
    return refs


def scan_bib_resources(source: str) -> list[str]:
    """Return the list of .bib resource names declared in the source.

    Names from ``\\bibliography{}`` are returned without extension (BibTeX convention);
    names from ``\\addbibresource{}`` are returned verbatim (biblatex always includes
    the extension). Callers resolve these against the document's directory.
    """
    text = _COMMENT_RE.sub("", source)
    names: list[str] = []
    for match in _BIBLIOGRAPHY_RE.finditer(text):
        names.extend(n.strip() for n in match.group(1).split(",") if n.strip())
    for match in _ADDBIBRESOURCE_RE.finditer(text):
        n = match.group(1).strip()
        if n:
            names.append(n)
    return names
