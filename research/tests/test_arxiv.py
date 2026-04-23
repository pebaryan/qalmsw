import gzip
import io
import tarfile
from unittest.mock import patch

from research import arxiv

_SAMPLE_ATOM = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>A Sample Paper Title</title>
    <summary>   This is the abstract.
It spans lines.   </summary>
  </entry>
</feed>"""


def _with_http(reply: bytes):
    return patch.object(arxiv, "_http_get", return_value=reply)


def test_fetch_metadata_parses_title_and_abstract():
    with _with_http(_SAMPLE_ATOM):
        meta = arxiv.fetch_metadata("2301.00001")
    assert meta is not None
    assert meta.title == "A Sample Paper Title"
    assert meta.abstract == "This is the abstract. It spans lines."


def test_fetch_metadata_returns_none_when_entry_missing():
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
    with _with_http(atom):
        assert arxiv.fetch_metadata("nope") is None


def test_fetch_metadata_returns_none_for_api_error_placeholder():
    atom = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/api/errors#malformed_id</id>
    <title>Error</title>
    <summary>bad id</summary>
  </entry>
</feed>"""
    with _with_http(atom):
        assert arxiv.fetch_metadata("bad") is None


def test_fetch_source_from_tarball():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"\\documentclass{article}\\begin{document}hi\\end{document}"
        info = tarfile.TarInfo(name="paper.tex")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        junk = b"ignored"
        info2 = tarfile.TarInfo(name="figure.pdf")
        info2.size = len(junk)
        tar.addfile(info2, io.BytesIO(junk))
    with _with_http(buf.getvalue()):
        files = arxiv.fetch_source("2301.00001")
    assert "paper.tex" in files
    assert "figure.pdf" not in files
    assert "\\begin{document}" in files["paper.tex"]


def test_fetch_source_from_single_gzipped_tex():
    tex = b"\\documentclass{article}\n\\begin{document}\nHello.\n\\end{document}\n"
    with _with_http(gzip.compress(tex)):
        files = arxiv.fetch_source("2301.00001")
    assert list(files.keys()) == ["main.tex"]
    assert "Hello." in files["main.tex"]


def test_fetch_source_returns_empty_for_non_tex_blob():
    with _with_http(b"not a tex file or tarball"):
        assert arxiv.fetch_source("2301.00001") == {}
