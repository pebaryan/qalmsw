"""Tests for the Image file existence checker."""
from pathlib import Path

from qalmsw.checkers import ImageChecker, Severity
from qalmsw.document import Document


def _doc(source: str, path: Path) -> Document:
    return Document(path=path, source=source, paragraphs=[])


def test_image_exists(tmp_path: Path):
    """An existing image file is silent."""
    img = tmp_path / "results.png"
    img.write_text("fake png")
    tex = tmp_path / "paper.tex"
    source = rf"\begin{{document}}\includegraphics{{{img.name}}}\end{{document}}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    assert findings == []


def test_image_missing_is_error(tmp_path: Path):
    """A missing image file is an error."""
    tex = tmp_path / "paper.tex"
    source = r"\begin{document}\includegraphics{missing_plot.png}\end{document}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    errors = [f for f in findings if f.severity == Severity.error]
    assert len(errors) >= 1
    assert "missing_plot.png" in errors[0].message


def test_no_extension_checks_common_formats(tmp_path: Path):
    """When no extension is given, try common image extensions."""
    img = tmp_path / "results.pdf"  # exists as .pdf
    img.write_text("fake pdf")
    tex = tmp_path / "paper.tex"
    source = r"\begin{document}\includegraphics{results}\end{document}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    assert findings == []


def test_multiple_images_some_missing(tmp_path: Path):
    """Only missing images are flagged."""
    img = tmp_path / "good.png"
    img.write_text("fake png")
    tex = tmp_path / "paper.tex"
    source = (
        r"\begin{document}"
        r"\includegraphics{good.png}"
        r"\includegraphics{bad.jpg}"
        r"\includegraphics{also_missing.png}"
        r"\end{document}"
    )
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    missing = [f for f in findings if "not found" in f.message]
    assert len(missing) == 2
    assert all(f.severity == Severity.error for f in missing)


def test_skips_non_image_extensions(tmp_path: Path):
    """Don't flag .tex, .cls, .bib paths as missing images."""
    tex = tmp_path / "paper.tex"
    source = r"\begin{document}\includegraphics{appendix.tex}\end{document}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    assert findings == []


def test_empty_graphics_path_is_ignored(tmp_path: Path):
    """Empty {} inside `includegraphics` is skipped."""
    tex = tmp_path / "paper.tex"
    source = r"\begin{document}\includegraphics{}\end{document}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    assert findings == []


def test_path_with_subdirectory(tmp_path: Path):
    """Images in subdirectories relative to the .tex file."""
    figures = tmp_path / "figures"
    figures.mkdir()
    img = figures / "arch.pdf"
    img.write_text("fake pdf")
    tex = tmp_path / "paper.tex"
    source = r"\begin{document}\includegraphics{figures/arch.pdf}\end{document}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    assert findings == []


def test_path_with_subdirectory_missing(tmp_path: Path):
    """Missing image in subdirectory is flagged."""
    tex = tmp_path / "paper.tex"
    source = r"\begin{document}\includegraphics{figures/missing.pdf}\end{document}"
    tex.write_text(source)
    findings = ImageChecker().check(_doc(source, tex))
    errors = [f for f in findings if f.severity == Severity.error]
    assert len(errors) == 1
