from qalmsw.parse import scan_bib_resources, scan_citations


def test_single_cite():
    refs = scan_citations("See \\cite{smith2020} for details.\n")
    assert [(r.key, r.line) for r in refs] == [("smith2020", 1)]


def test_multiple_keys_in_one_cite():
    refs = scan_citations("\\cite{a,b, c}\n")
    assert [r.key for r in refs] == ["a", "b", "c"]


def test_citep_with_pre_and_post_notes():
    refs = scan_citations("\\citep[see][p.~42]{jones1999}\n")
    assert [(r.key, r.line) for r in refs] == [("jones1999", 1)]


def test_line_tracking_across_multiple():
    source = "first line\n\\cite{a}\n\n\\citet{b}\n"
    refs = scan_citations(source)
    assert [(r.key, r.line) for r in refs] == [("a", 2), ("b", 4)]


def test_cite_in_comment_is_ignored():
    refs = scan_citations("real text %\\cite{hidden}\n\\cite{visible}\n")
    assert [r.key for r in refs] == ["visible"]


def test_bibliography_directive():
    names = scan_bib_resources("\\bibliography{refs,extra}\n")
    assert names == ["refs", "extra"]


def test_addbibresource_directive():
    names = scan_bib_resources("\\addbibresource{bibliography.bib}\n")
    assert names == ["bibliography.bib"]
