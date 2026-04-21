from qalmsw.parse import parse_sections


def test_no_sections_returns_single_untitled():
    source = "\\begin{document}\nSome text.\nMore text.\n\\end{document}\n"
    sections = parse_sections(source)
    assert len(sections) == 1
    assert sections[0].title == ""
    assert "Some text." in sections[0].text
    assert sections[0].start_line == 2


def test_single_section_tracks_title_and_line():
    source = (
        "\\begin{document}\n"
        "\\section{Introduction}\n"
        "Body of intro.\n"
        "\\end{document}\n"
    )
    sections = parse_sections(source)
    assert len(sections) == 1
    assert sections[0].title == "Introduction"
    assert sections[0].start_line == 2
    assert "Body of intro." in sections[0].text


def test_multiple_sections_split_and_track_lines():
    source = (
        "\\begin{document}\n"
        "\\section{Intro}\n"
        "first body\n"
        "\n"
        "\\section{Method}\n"
        "second body\n"
        "\\end{document}\n"
    )
    sections = parse_sections(source)
    assert [s.title for s in sections] == ["Intro", "Method"]
    assert sections[0].start_line == 2
    assert sections[1].start_line == 5
    assert "first body" in sections[0].text
    assert "second body" in sections[1].text
    assert "second body" not in sections[0].text


def test_starred_section_supported():
    source = "\\begin{document}\n\\section*{Unnumbered}\nbody\n\\end{document}\n"
    sections = parse_sections(source)
    assert sections[0].title == "Unnumbered"


def test_comments_dont_introduce_phantom_section():
    source = (
        "\\begin{document}\n"
        "% \\section{fake}\n"
        "\\section{Real}\n"
        "body\n"
        "\\end{document}\n"
    )
    sections = parse_sections(source)
    assert [s.title for s in sections] == ["Real"]
