from pathlib import Path

from qalmsw.document import Document
from qalmsw.parse import resolve_includes


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_no_includes_is_passthrough(tmp_path: Path):
    main = tmp_path / "main.tex"
    body = "\\begin{document}\nHello world.\n\\end{document}\n"
    _write(main, body)
    source, line_map = resolve_includes(main)
    assert source == body
    assert len(line_map) == body.count("\n")
    assert all(entry.file == main for entry in line_map)
    assert [e.line for e in line_map] == list(range(1, len(line_map) + 1))


def test_input_inlined(tmp_path: Path):
    main = tmp_path / "main.tex"
    intro = tmp_path / "sections" / "intro.tex"
    _write(intro, "Intro line one.\nIntro line two.\n")
    _write(main, "\\begin{document}\n\\input{sections/intro}\n\\end{document}\n")
    source, line_map = resolve_includes(main)
    assert "Intro line one." in source
    assert "Intro line two." in source
    # The line containing "Intro line one." should map back to intro.tex:1.
    lines = source.split("\n")
    idx = lines.index("Intro line one.")
    assert line_map[idx].file == intro
    assert line_map[idx].line == 1
    idx2 = lines.index("Intro line two.")
    assert line_map[idx2].file == intro
    assert line_map[idx2].line == 2


def test_include_adds_tex_suffix(tmp_path: Path):
    main = tmp_path / "main.tex"
    sub = tmp_path / "part.tex"
    _write(sub, "Sub content.\n")
    _write(main, "\\input{part}\n")
    source, line_map = resolve_includes(main)
    assert "Sub content." in source
    lines = source.split("\n")
    idx = lines.index("Sub content.")
    assert line_map[idx].file == sub


def test_missing_include_is_tolerated(tmp_path: Path):
    main = tmp_path / "main.tex"
    _write(main, "Before\n\\input{does_not_exist}\nAfter\n")
    source, line_map = resolve_includes(main)
    assert "Before" in source
    assert "After" in source
    assert "qalmsw" in source  # placeholder comment emitted


def test_cycle_detected(tmp_path: Path):
    a = tmp_path / "a.tex"
    b = tmp_path / "b.tex"
    _write(a, "A\n\\input{b}\n")
    _write(b, "B\n\\input{a}\n")
    source, _ = resolve_includes(a)
    # Should not infinite-loop; cycle back to a is refused.
    assert source.count("cycle detected") >= 1


def test_nested_includes(tmp_path: Path):
    main = tmp_path / "main.tex"
    mid = tmp_path / "mid.tex"
    leaf = tmp_path / "leaf.tex"
    _write(leaf, "Leaf content.\n")
    _write(mid, "Mid content.\n\\input{leaf}\n")
    _write(main, "\\input{mid}\n")
    source, line_map = resolve_includes(main)
    assert "Mid content." in source
    assert "Leaf content." in source
    lines = source.split("\n")
    assert line_map[lines.index("Leaf content.")].file == leaf
    assert line_map[lines.index("Mid content.")].file == mid


def test_input_in_comment_not_followed(tmp_path: Path):
    main = tmp_path / "main.tex"
    _write(main, "Body\n% \\input{ignored}\n")
    source, _ = resolve_includes(main)
    # The commented line is kept verbatim (we preserve it as-is); we just don't follow it.
    assert "ignored" in source  # text preserved
    # But no separate file was created, so no expansion occurred; line count matches input.
    assert source.count("\n") == 2


def test_document_load_attributes_paragraphs_to_origin(tmp_path: Path):
    main = tmp_path / "main.tex"
    intro = tmp_path / "intro.tex"
    _write(intro, "Paragraph from intro with enough words.\n")
    _write(
        main,
        "\\begin{document}\n"
        "\\input{intro}\n"
        "\n"
        "Paragraph in main.\n"
        "\\end{document}\n",
    )
    doc = Document.load(main)
    texts = [p.text for p in doc.paragraphs]
    assert "Paragraph from intro with enough words." in texts
    assert "Paragraph in main." in texts
    from_intro = next(p for p in doc.paragraphs if "from intro" in p.text)
    from_main = next(p for p in doc.paragraphs if "in main" in p.text)
    assert from_intro.file == intro
    assert from_intro.start_line == 1
    assert from_main.file == main
