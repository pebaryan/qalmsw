from pathlib import Path

from qalmsw.bib import parse_bib_text


def _parse(text: str):
    return parse_bib_text(text, source=Path("test.bib"))


def test_simple_entry():
    entries = _parse("@article{smith2020, title={Hello}, author={Smith}}\n")
    assert len(entries) == 1
    assert entries[0].key == "smith2020"
    assert entries[0].entry_type == "article"
    assert entries[0].line == 1


def test_multiple_entries_track_lines():
    text = (
        "@book{a2000, title={A}}\n"
        "\n"
        "@inproceedings{b2001,\n"
        "  title={B},\n"
        "}\n"
    )
    entries = _parse(text)
    assert [(e.key, e.line) for e in entries] == [("a2000", 1), ("b2001", 3)]


def test_string_preamble_and_comment_entries_are_ignored():
    text = (
        "@string{me = \"John Doe\"}\n"
        "@preamble{\"hi\"}\n"
        "@comment{ignored}\n"
        "@article{real2020, title={X}}\n"
    )
    entries = _parse(text)
    assert [e.key for e in entries] == ["real2020"]


def test_line_comment_entries_are_stripped():
    text = "% @article{hidden, title={x}}\n@article{visible, title={y}}\n"
    entries = _parse(text)
    assert [e.key for e in entries] == ["visible"]


def test_entry_type_is_lowercased():
    entries = _parse("@ARTICLE{k, title={T}}\n")
    assert entries[0].entry_type == "article"
