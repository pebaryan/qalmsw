"""Tests for CLI batch mode and retrieval backend switching."""
from pathlib import Path

from qalmsw.retrieval import search_by_title, set_backend
from qalmsw.retrieval.scholar import search_by_title as gs_search
from qalmsw.retrieval.semantic_scholar import search_by_title as ss_search


def test_default_backend_is_semantic_scholar():
    """Module-level search_by_title should point to Semantic Scholar by default."""
    assert search_by_title is ss_search


def test_set_backend_google_scholar():
    """Switching to google-scholar patches the module-level function."""
    import qalmsw.retrieval as mod
    original = mod.search_by_title
    set_backend("google-scholar")
    try:
        assert mod.search_by_title is gs_search
    finally:
        # Restore
        set_backend("semantic-scholar")
    assert mod.search_by_title is original


def test_set_backend_semantic_scholar():
    """Switching back to semantic-scholar restores the original."""
    import qalmsw.retrieval as mod
    set_backend("google-scholar")
    set_backend("semantic-scholar")
    assert mod.search_by_title is ss_search


def test_set_backend_unknown_raises():
    """Unknown backend name raises ValueError."""
    import pytest
    with pytest.raises(ValueError, match="Unknown retrieval backend"):
        set_backend("bing")


def test_resolve_files_single(tmp_path: Path):
    """Single existing .tex file is returned as-is."""
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}\begin{document}hello\end{document}")
    from qalmsw.cli import _resolve_files
    resolved = _resolve_files([tex])
    assert len(resolved) == 1
    assert resolved[0] == tex


def test_resolve_files_glob(tmp_path: Path):
    """Glob pattern expands to matching .tex files."""
    (tmp_path / "ch1.tex").write_text("chapter 1")
    (tmp_path / "ch2.tex").write_text("chapter 2")
    (tmp_path / "notes.txt").write_text("not a tex file")
    from qalmsw.cli import _resolve_files
    resolved = _resolve_files([tmp_path / "ch*.tex"])
    assert len(resolved) == 2
    names = {f.name for f in resolved}
    assert names == {"ch1.tex", "ch2.tex"}


def test_resolve_files_no_match(tmp_path: Path):
    """Glob with no matches returns empty list."""
    from qalmsw.cli import _resolve_files
    resolved = _resolve_files([tmp_path / "nonexistent*.tex"])
    assert resolved == []
