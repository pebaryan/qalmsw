"""Tests for the LLM Artifact Checker."""
from pathlib import Path

from qalmsw.checkers import ArtifactChecker, Severity
from qalmsw.document import Document


def _doc(source: str) -> Document:
    return Document(path=Path("paper.tex"), source=source, paragraphs=[])


# ---- Meta-comment patterns ----

def test_here_is_summary():
    source = r"""\begin{document}
Here is a 200-word summary of the results.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "meta-comment" in f.message and "summary" in f.message]
    assert len(matched) >= 1
    assert matched[0].severity == Severity.error
    assert matched[0].excerpt is not None
    assert "200-word" in matched[0].excerpt


def test_would_you_like_me_to():
    source = r"""\begin{document}
Here is the analysis. Would you like me to make any changes?
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "meta-comment" in f.message]
    assert len(matched) >= 1
    assert matched[0].severity == Severity.error


def test_id_be_happy_to():
    source = r"""\begin{document}
I'd be happy to help you with this section.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "meta-comment" in f.message]
    assert len(matched) >= 1


# ---- Placeholder patterns ----

def test_fill_in_with_real_data():
    source = r"""\begin{document}
Table~\ref{tab:results} shows the performance. Fill in with the real numbers.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "placeholder" in f.message]
    assert len(matched) >= 1
    assert matched[0].severity == Severity.error


def test_illustrative_data():
    source = r"""\begin{document}
The data in this table is illustrative only.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "illustrative" in f.message]
    assert len(matched) >= 1


def test_insert_your_content_here():
    source = r"""\begin{document}
Insert your content here.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "insert your content" in f.message]
    assert len(matched) >= 1


def test_placeholder_caption():
    source = r"""\begin{document}
\begin{figure}
\caption{Placeholder caption text}
\end{figure}
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "Phantom caption" in f.message]
    assert len(matched) >= 1
    assert matched[0].severity == Severity.error


def test_placeholder_label():
    source = r"""\begin{document}
\label{fig:placeholder}
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "Phantom label" in f.message]
    assert len(matched) >= 1


# ---- Self-awareness patterns ----

def test_as_an_ai_language_model():
    source = r"""\begin{document}
As an AI language model, I cannot browse the internet.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "self-reference" in f.message]
    assert len(matched) >= 1


def test_i_cannot_provide():
    source = r"""\begin{document}
I can't provide the specific implementation details.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "refusal" in f.message]
    assert len(matched) >= 1


def test_im_sorry():
    source = r"""\begin{document}
I'm sorry, but I cannot access real-time data.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "sorry" in f.message]
    assert len(matched) >= 1


# ---- LaTeX artifact patterns ----

def test_lipsum():
    source = r"""\begin{document}
\lipsum[1-4]
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "\\lipsum" in f.message]
    assert len(matched) >= 1
    assert matched[0].severity == Severity.warning


def test_todo_marker():
    source = r"""\begin{document}
TODO: add experimental results here.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "TODO" in f.message]
    assert len(matched) >= 1


# ---- Clean document produces no findings ----

def test_clean_document_no_findings():
    source = r"""\begin{document}
We propose a novel method for geometric algebra flow matching.
Our approach outperforms existing methods across three benchmarks.
\bibliography{refs}
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    assert findings == []


# ---- Preamble scanning ----

def test_preamble_artifact():
    source = r"""\label{sec:placeholder}
\begin{document}
Clean body text here.
\end{document}"""
    findings = ArtifactChecker().check(_doc(source))
    matched = [f for f in findings if "Phantom label" in f.message]
    assert len(matched) >= 1
