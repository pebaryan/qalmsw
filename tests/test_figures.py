"""Tests for the Figure/Table Completeness Checker."""
from pathlib import Path

from qalmsw.checkers import FigureTableChecker, Severity
from qalmsw.document import Document


def _doc(source: str) -> Document:
    return Document(path=Path("paper.tex"), source=source, paragraphs=[])


def test_well_formed_figure_passes():
    source = r"""\begin{document}
Content before.
\begin{figure}
\centering
\includegraphics{results.png}
\caption{Performance comparison across benchmarks.}
\label{fig:results}
\end{figure}
As shown in Figure~\ref{fig:results}.
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    assert findings == []


def test_well_formed_table_passes():
    source = r"""\begin{document}
\begin{table}
\caption{Experimental parameters.}
\label{tab:params}
\begin{tabular}{ll}
alpha & 0.1 \\
beta  & 0.2
\end{tabular}
\end{table}
Table~\ref{tab:params} lists the settings.
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    assert findings == []


def test_missing_caption_is_error():
    source = r"""\begin{document}
\begin{figure}
\includegraphics{plot.png}
\label{fig:plot}
\end{figure}
See Figure~\ref{fig:plot}.
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    # Should flag missing \caption{}, but NOT orphaned label (it IS in \ref{})
    missing = [f for f in findings if "missing" in f.message.lower()]
    assert len(missing) == 1
    assert missing[0].severity == Severity.error


def test_placeholder_caption_detected():
    source = r"""\begin{document}
\begin{figure}
\caption{Insert caption here}
\label{fig:placeholder}
\end{figure}
See Figure~\ref{fig:placeholder}.
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    placeholder = [f for f in findings if "placeholder" in f.message]
    assert len(placeholder) >= 1
    assert placeholder[0].severity == Severity.error


def test_orphaned_label_warning():
    source = r"""\begin{document}
\begin{figure}
\caption{Our proposed architecture.}
\label{fig:arch}
\end{figure}
(No reference to this figure in the body.)
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    orphaned = [f for f in findings if "not referenced" in f.message]
    assert len(orphaned) >= 1
    assert orphaned[0].severity == Severity.warning


def test_no_floats_yields_no_findings():
    source = r"""\begin{document}
Just prose with no figures or tables.
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    assert findings == []


def test_empty_float_warning():
    source = r"""\begin{document}
\begin{figure}
\caption{A figure with no real content.}
\label{fig:empty}
\end{figure}
See Figure~\ref{fig:empty}.
\end{document}"""
    findings = FigureTableChecker().check(_doc(source))
    empty = [f for f in findings if "Near-empty" in f.message or "Near-empty" in f.message]
    # The float has no graphics, no tabular — just \caption and \label
    # This should be flagged
    assert len(empty) >= 1
    assert empty[0].severity == Severity.warning
