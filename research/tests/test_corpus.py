from research.arxiv import ArxivMetadata
from research.corpus import sample_triples_from_paper


def _meta(arxiv_id: str) -> ArxivMetadata:
    return ArxivMetadata(
        arxiv_id=arxiv_id,
        title=f"Title for {arxiv_id}",
        abstract=f"Abstract for {arxiv_id}. It has two sentences.",
    )


def _scripted_fetch(ids_to_meta: dict[str, ArxivMetadata | None]):
    def fetch(aid: str) -> ArxivMetadata | None:
        return ids_to_meta.get(aid)
    return fetch


def test_resolves_arxiv_ids_from_bib_eprint_field():
    tex = (
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "Some claim about attention mechanisms~\\cite{vaswani2017} is cited here.\n"
        "\\end{document}\n"
    )
    bib = (
        "@inproceedings{vaswani2017,\n"
        "  title={Attention Is All You Need},\n"
        "  author={Vaswani, Ashish},\n"
        "  eprint={1706.03762},\n"
        "}\n"
    )
    fetch = _scripted_fetch({"1706.03762": _meta("1706.03762")})
    triples = sample_triples_from_paper(
        "test/0001", {"paper.tex": tex}, bib, fetch_meta=fetch, sleep_between=0
    )
    assert len(triples) == 1
    t = triples[0]
    assert t.cite_key == "vaswani2017"
    assert t.cited_arxiv_id == "1706.03762"
    assert "Attention" in t.cited_title


def test_resolves_arxiv_id_from_url_field():
    tex = (
        "\\begin{document}\n"
        "Cited work shows something~\\cite{foo}.\n"
        "\\end{document}\n"
    )
    bib = "@article{foo, url={https://arxiv.org/abs/2301.99999}}\n"
    fetch = _scripted_fetch({"2301.99999": _meta("2301.99999")})
    triples = sample_triples_from_paper(
        "test/0002", {"paper.tex": tex}, bib, fetch_meta=fetch, sleep_between=0
    )
    assert len(triples) == 1
    assert triples[0].cited_arxiv_id == "2301.99999"


def test_skips_cite_keys_without_arxiv_id():
    tex = "\\begin{document}\nClaim~\\cite{noarxiv}.\n\\end{document}\n"
    bib = "@article{noarxiv, title={A Book}, publisher={Springer}}\n"
    fetch = _scripted_fetch({})
    triples = sample_triples_from_paper(
        "test/0003", {"paper.tex": tex}, bib, fetch_meta=fetch, sleep_between=0
    )
    assert triples == []


def test_respects_max_per_paper():
    tex = (
        "\\begin{document}\n"
        "First paragraph~\\cite{a}.\n"
        "\n"
        "Second paragraph~\\cite{b}.\n"
        "\n"
        "Third paragraph~\\cite{c}.\n"
        "\\end{document}\n"
    )
    bib = (
        "@article{a, eprint={2201.00001}}\n"
        "@article{b, eprint={2201.00002}}\n"
        "@article{c, eprint={2201.00003}}\n"
    )
    fetch = _scripted_fetch(
        {f"2201.0000{i}": _meta(f"2201.0000{i}") for i in (1, 2, 3)}
    )
    triples = sample_triples_from_paper(
        "test/0004", {"paper.tex": tex}, bib,
        fetch_meta=fetch, sleep_between=0, max_per_paper=2,
    )
    assert len(triples) == 2


def test_caches_abstract_across_calls():
    tex = "\\begin{document}\nA~\\cite{a}.\n\n B~\\cite{b}.\n\\end{document}\n"
    bib = (
        "@article{a, eprint={2201.00001}}\n"
        "@article{b, eprint={2201.00001}}\n"  # same arxiv id as a
    )
    calls: list[str] = []

    def fetch(aid: str):
        calls.append(aid)
        return _meta(aid)

    cache: dict = {}
    sample_triples_from_paper(
        "test/0005", {"paper.tex": tex}, bib,
        fetch_meta=fetch, sleep_between=0, abstract_cache=cache,
    )
    assert len(calls) == 1
    assert "2201.00001" in cache


def test_inline_bibliography_is_used_when_no_bib_text():
    tex = (
        "\\begin{document}\n"
        "Claim~\\cite{foo}.\n"
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{foo} Author, Title, arxiv.org/abs/2302.12345, 2023.\n"
        "\\end{thebibliography}\n"
        "\\end{document}\n"
    )
    fetch = _scripted_fetch({"2302.12345": _meta("2302.12345")})
    triples = sample_triples_from_paper(
        "test/0006", {"paper.tex": tex}, bib_text=None,
        fetch_meta=fetch, sleep_between=0,
    )
    assert len(triples) == 1
    assert triples[0].cited_arxiv_id == "2302.12345"
