from pathlib import Path

from qalmsw.bib import extract_inline_bibitems
from qalmsw.parse.includes import LineMapEntry


def test_extracts_keys_from_thebibliography():
    src = (
        "\\begin{document}\n"
        "Body.\n"
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{foo} A. Author, ``A Title'', Venue, 2020.\n"
        "\\bibitem{bar} B. Author, Something, 2021.\n"
        "\\end{thebibliography}\n"
        "\\end{document}\n"
    )
    entries = extract_inline_bibitems(src, default_file=Path("paper.tex"))
    keys = [e.key for e in entries]
    assert keys == ["foo", "bar"]
    assert entries[0].entry_type == "bibitem"
    assert entries[0].file == Path("paper.tex")
    assert entries[0].line == 4


def test_title_guessed_from_quoted_text():
    src = (
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{foo} A. Author, ``Attention Is All You Need'', NeurIPS, 2017.\n"
        "\\end{thebibliography}\n"
    )
    entries = extract_inline_bibitems(src)
    assert entries[0].title == "Attention Is All You Need"


def test_title_guessed_from_textit():
    src = (
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{foo} A. Author, \\textit{A Book Title}, Publisher, 2020.\n"
        "\\end{thebibliography}\n"
    )
    entries = extract_inline_bibitems(src)
    assert entries[0].title == "A Book Title"


def test_missing_title_is_empty():
    src = (
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{foo} A. Author. No title markup. 2020.\n"
        "\\end{thebibliography}\n"
    )
    entries = extract_inline_bibitems(src)
    assert entries[0].title == ""


def test_no_thebibliography_yields_nothing():
    src = "\\begin{document}\nNo bib here.\n\\end{document}\n"
    assert extract_inline_bibitems(src) == []


def test_bibitem_with_optional_label():
    src = (
        "\\begin{thebibliography}{99}\n"
        "\\bibitem[Smith2020]{smith2020} Smith, ``X''.\n"
        "\\end{thebibliography}\n"
    )
    entries = extract_inline_bibitems(src)
    assert entries[0].key == "smith2020"


def test_line_map_attributes_to_original_file():
    src = (
        "\\begin{thebibliography}{99}\n"  # combined line 1
        "\\bibitem{foo} text.\n"  # combined line 2
        "\\end{thebibliography}\n"  # combined line 3
    )
    main = Path("main.tex")
    refs = Path("refs.tex")
    line_map = [
        LineMapEntry(refs, 10),
        LineMapEntry(refs, 11),
        LineMapEntry(refs, 12),
    ]
    entries = extract_inline_bibitems(src, line_map=line_map, default_file=main)
    assert entries[0].file == refs
    assert entries[0].line == 11
