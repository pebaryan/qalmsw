"""Tests for the ambiguity checker."""

import json
from pathlib import Path

from qalmsw.checkers import AmbiguityChecker, Severity
from qalmsw.checkers.ambiguity import screen, split_sentences
from qalmsw.document import Document
from qalmsw.parse import Paragraph

PAIRS = json.loads(
    (Path(__file__).parent / "fixtures" / "ambiguity_pairs.json").read_text(encoding="utf-8")
)["pairs"]


def _doc(*paragraphs: Paragraph) -> Document:
    return Document(path=Path("paper.tex"), source="", paragraphs=list(paragraphs))


class FakeLLM:
    """Answers the read pass with `read` and the verify pass with `verify`."""

    def __init__(self, read: dict, verify: dict | None = None) -> None:
        self.read = read
        self.verify = verify or {"plausible": True, "material": True, "reason": "ok"}
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict:
        self.calls.append((system, user))
        return self.verify if "skeptical" in system else self.read


def test_split_sentences_keeps_abbreviations_and_offsets():
    text = "We follow Smith et al. in using Fig. 2 settings. This helps. It is e.g. shown below."
    sentences = split_sentences(text)
    assert [s for s, _ in sentences] == [
        "We follow Smith et al. in using Fig. 2 settings.",
        "This helps.",
        "It is e.g. shown below.",
    ]
    for sentence, offset in sentences:
        assert text[offset : offset + len(sentence)] == sentence


def test_screen_flags_every_vague_benchmark_sentence():
    missed = [pair["id"] for pair in PAIRS if not screen(pair["vague"])]
    assert missed == []


def test_screen_suppresses_quantified_comparisons():
    assert screen("Accuracy is 2.1 points higher than the baseline in Table 3.") == []
    [candidate] = screen("Accuracy is higher than the baseline.")
    assert candidate.cues == ("comparison without a baseline",)


def test_screen_ignores_sentences_without_cues():
    assert screen("We train for 20 epochs with a batch size of 64.") == []


def test_finding_shows_readings_and_question_on_the_right_line():
    para = Paragraph(
        text="We normalize the features and remove outliers.\nThis improves stability.",
        start_line=10,
        end_line=11,
    )
    llm = FakeLLM(
        {
            "findings": [
                {
                    "id": 1,
                    "phrase": "This",
                    "readings": [
                        "normalization improves stability",
                        "outlier removal improves stability",
                    ],
                    "question": "Which step improves stability?",
                }
            ]
        }
    )
    [finding] = AmbiguityChecker(llm).check(_doc(para))
    assert finding.checker == "ambiguity"
    assert finding.severity == Severity.warning
    assert finding.line == 11
    assert finding.excerpt == "This"
    assert (
        "(a) normalization improves stability; (b) outlier removal improves stability"
        in finding.message
    )
    assert finding.suggestion.startswith("Which step improves stability?")
    assert len(llm.calls) == 2  # one read pass, one verification


def test_verifier_drops_implausible_or_immaterial_readings():
    para = Paragraph(text="The model is robust.", start_line=1, end_line=1)
    read = {"findings": [{"id": 1, "phrase": "robust", "readings": ["a", "b"], "question": "q"}]}
    assert (
        AmbiguityChecker(FakeLLM(read, {"plausible": True, "material": False})).check(_doc(para))
        == []
    )
    assert (
        AmbiguityChecker(FakeLLM(read, {"plausible": False, "material": True})).check(_doc(para))
        == []
    )
    assert (
        len(AmbiguityChecker(FakeLLM(read, {"plausible": False}), verify=False).check(_doc(para)))
        == 1
    )


def test_malformed_or_single_reading_proposals_are_ignored():
    para = Paragraph(text="The model is robust.", start_line=1, end_line=1)
    read = {
        "findings": [
            {"id": 7, "phrase": "robust", "readings": ["a", "b"]},  # no such candidate
            {"id": 1, "phrase": "robust", "readings": ["only one"]},
            {"id": 1, "phrase": "robust", "readings": ["same", "same"]},
            "not a dict",
        ]
    }
    assert AmbiguityChecker(FakeLLM(read)).check(_doc(para)) == []


def test_phrase_not_in_sentence_falls_back_to_sentence():
    para = Paragraph(text="The model is robust.", start_line=3, end_line=3)
    read = {
        "findings": [
            {"id": 1, "phrase": "invented phrase", "readings": ["a", "b"], "question": "q"}
        ]
    }
    [finding] = AmbiguityChecker(FakeLLM(read)).check(_doc(para))
    assert finding.excerpt == "The model is robust."


def test_paragraphs_without_candidates_cost_no_llm_calls():
    para = Paragraph(
        text="We train for 20 epochs with a batch size of 64.", start_line=1, end_line=1
    )
    llm = FakeLLM({"findings": []})
    assert AmbiguityChecker(llm).check(_doc(para)) == []
    assert llm.calls == []


def test_screen_off_sends_every_prose_sentence():
    para = Paragraph(
        text="We train for 20 epochs with a batch size of 64.", start_line=1, end_line=1
    )
    llm = FakeLLM({"findings": []})
    AmbiguityChecker(llm, screen=False).check(_doc(para))
    assert len(llm.calls) == 1
    assert "1. We train for 20 epochs" in llm.calls[0][1]
