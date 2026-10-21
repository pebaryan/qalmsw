"""ReferenceChecker delegating to the LitKG reference backend."""
import json
from pathlib import Path

import pytest

from qalmsw.bib import BibEntry, parse_bib_file
from qalmsw.checkers import ReferenceChecker, Severity
from qalmsw.document import Document

api = pytest.importorskip("litkg.api")
from litkg.verify import Response  # noqa: E402

RESNET = {
    "title": "Deep Residual Learning for Image Recognition",
    "author": [{"family": "He", "given": "Kaiming"}, {"family": "Zhang", "given": "Xiangyu"}],
    "issued": {"date-parts": [[2016]]},
    "DOI": "10.1109/CVPR.2016.90",
    "type": "paper-conference",
}


class FakeRegistry:
    """doi.org knows one DOI; every search finds nothing."""

    def get(self, url: str, accept: str = "application/json") -> Response:
        if url.startswith("https://doi.org/"):
            if url.lower().endswith("10.1109/cvpr.2016.90"):
                return Response(200, json.dumps(RESNET))
            return Response(404, "")
        if "api.crossref.org" in url:
            return Response(200, json.dumps({"message": {"items": []}}))
        if "api.openalex.org" in url:
            return Response(200, json.dumps({"results": []}))
        return Response(404, "")


BIB = r"""
@inproceedings{he2016,
  title = {Deep Residual Learning for Image Recognition},
  author = {He, Kaiming and Zhang, Xiangyu},
  year = {2016},
  doi = {10.1109/CVPR.2016.90},
}
@article{fakeauthors,
  title = {Deep Residual Learning for Image Recognition},
  author = {Smith, Alice and Jones, Bob},
  year = {2016},
  doi = {10.1109/CVPR.2016.90},
}
@article{ghost,
  title = {Quantum Gradient Descent for Alignment},
  author = {Doe, Jane},
  year = {2023},
  doi = {10.5555/does.not.exist},
}
"""


def _doc() -> Document:
    return Document(path=Path("paper.tex"), source="", paragraphs=[])


def _backend(**kwargs):
    return api.ReferenceBackend(fetcher=FakeRegistry(), workers=1, **kwargs)


def test_litkg_backend_catches_wrong_authors_and_nonexistent_doi(tmp_path: Path) -> None:
    bib = tmp_path / "refs.bib"
    bib.write_text(BIB, encoding="utf-8")
    entries = parse_bib_file(bib)

    findings = ReferenceChecker(entries, backend=_backend()).check(_doc())

    keys = ("he2016", "fakeauthors", "ghost")
    by_key = {key: [f for f in findings if f"'{key}'" in f.message] for key in keys}
    assert by_key["he2016"] == []
    [authors] = [f for f in by_key["fakeauthors"] if "(author-mismatch)" in f.message]
    assert authors.severity == Severity.error
    assert authors.file == str(bib)
    assert authors.line == next(e.line for e in entries if e.key == "fakeauthors")
    assert authors.suggestion and "doi:10.1109/cvpr.2016.90" in authors.suggestion
    [ghost] = [f for f in by_key["ghost"] if "(doi-not-found)" in f.message]
    assert ghost.severity == Severity.error


def test_litkg_backend_handles_inline_bibitems() -> None:
    entry = BibEntry(
        key="inline",
        entry_type="bibitem",
        file=Path("paper.tex"),
        line=12,
        title="Deep Residual Learning for Image Recognition",
        author="He, Kaiming",
        doi="10.1109/CVPR.2016.90",
    )
    findings = ReferenceChecker([entry], backend=_backend()).check(_doc())
    assert all(f.severity != Severity.error for f in findings)


def test_explicit_verify_function_overrides_backend() -> None:
    entry = BibEntry(key="x", entry_type="article", file=Path("refs.bib"), line=1, doi="10.1/x")
    checker = ReferenceChecker([entry], verify=lambda e: (True, "ok"), backend=_backend())
    assert checker.check(_doc()) == []
