from qalmsw.parse import has_prose, parse_paragraphs


def test_simple_paragraphs():
    source = (
        "\\begin{document}\n"
        "First paragraph here.\n"
        "Still first.\n"
        "\n"
        "Second paragraph.\n"
        "\\end{document}\n"
    )
    paras = parse_paragraphs(source)
    assert len(paras) == 2
    assert paras[0].text == "First paragraph here.\nStill first."
    assert paras[0].start_line == 2
    assert paras[0].end_line == 3
    assert paras[1].text == "Second paragraph."
    assert paras[1].start_line == 5
    assert paras[1].end_line == 5


def test_comments_stripped_but_lines_preserved():
    source = "\\begin{document}\nLine one. % a comment\nLine two.\n\\end{document}\n"
    paras = parse_paragraphs(source)
    assert len(paras) == 1
    assert "comment" not in paras[0].text
    assert paras[0].start_line == 2


def test_escaped_percent_not_a_comment():
    source = "\\begin{document}\n50\\% efficiency.\n\\end{document}\n"
    paras = parse_paragraphs(source)
    assert paras[0].text == "50\\% efficiency."


def test_no_begin_document():
    source = "First line.\n\nSecond line."
    paras = parse_paragraphs(source)
    assert len(paras) == 2
    assert paras[0].start_line == 1
    assert paras[1].start_line == 3


def test_content_after_preamble_tracks_lines():
    source = (
        "\\documentclass{article}\n"
        "\\usepackage{amsmath}\n"
        "\\begin{document}\n"
        "Real content.\n"
        "\\end{document}\n"
    )
    paras = parse_paragraphs(source)
    assert len(paras) == 1
    assert paras[0].start_line == 4


def test_has_prose_rejects_bare_commands():
    assert not has_prose("\\maketitle")
    assert not has_prose("\\section{Introduction}")
    assert not has_prose("\\begin{equation}\\end{equation}")


def test_has_prose_accepts_real_sentences():
    assert has_prose("This paper investigates attention mechanisms.")


def test_has_prose_accepts_prose_with_latex_commands():
    assert has_prose("Recent work~\\cite{foo} shows that self-attention scales well.")


def test_inline_thebibliography_is_excluded_from_body():
    source = (
        "\\begin{document}\n"
        "Real body content with enough words here.\n"
        "\n"
        "\\begin{thebibliography}{99}\n"
        "\\bibitem{foo} A. Author, Title, Venue, 2020.\n"
        "\\end{thebibliography}\n"
        "\\end{document}\n"
    )
    paras = parse_paragraphs(source)
    assert len(paras) == 1
    assert "bibitem" not in paras[0].text
    assert "thebibliography" not in paras[0].text
