"""Ambiguity checker: sentences a reader could take more than one way.

AI-drafted prose tends to be *consistent with* what the author meant while also being
consistent with readings the author did not intend. Proofreading does not catch this:
the author checks "does this say what I meant?" (it does), not "what else could it
mean?" (the curse of knowledge hides the answer). So this checker never asks the LLM
"is this vague?". It asks the LLM to read as a stranger and produce the competing
readings, and only reports a sentence when it can show at least two that differ.

Pipeline per paragraph:

1. **Screen** (deterministic, free): split into sentences and keep those with known
   vagueness cues — unquantified magnitudes, comparisons without a baseline, unscoped
   claims ("robust", "generalizes"), and "This/It ..." with no noun. Each cue becomes a
   hint for the LLM. ``screen=False`` sends every sentence instead.
2. **Read as a stranger** (one LLM call per paragraph with candidates): for each
   candidate, list the distinct readings a careful reader in the field could hold, or
   none if the paragraph pins the meaning down.
3. **Verify** (one LLM call per proposed finding): an independent pass that sees only the
   paragraph, the phrase, and the readings, and confirms that each reading is plausible
   *in context* and that they lead to materially different conclusions. This is where
   precise hedging ("may", "in our experiments") and terms defined nearby get dropped.

Findings are warnings: ambiguity is a judgement for the author, not a CI gate.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from qalmsw._concurrency import ordered_parallel_map
from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document
from qalmsw.llm import LLMClient
from qalmsw.parse import Paragraph, has_prose

# --------------------------------------------------------------------------- screen

# Abbreviations whose trailing period does not end a sentence.
_ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "et al.",
    "etc.",
    "cf.",
    "vs.",
    "Fig.",
    "Figs.",
    "Eq.",
    "Eqs.",
    "Sec.",
    "Tab.",
    "Ref.",
    "approx.",
    "resp.",
    "No.",
    "Dr.",
    "Prof.",
)
_SENTENCE_END_RE = re.compile(r"[.!?](?:['\")\]}]*)\s+(?=[A-Z\\(\"'`])")
_NUMBER_RE = re.compile(r"\d")
_INLINE_MATH_RE = re.compile(r"\$[^$]*\$")

_CUES: list[tuple[str, re.Pattern[str], str]] = [
    (
        "unquantified magnitude",
        re.compile(
            r"\b(?:significant(?:ly)?|substantial(?:ly)?|considerabl[ey]|dramatic(?:ally)?|"
            r"marked(?:ly)?|greatly|largely|slightly|notabl[ey]|remarkabl[ey])\b",
            re.IGNORECASE,
        ),
        "how large? 'significant' may mean statistically significant or just large",
    ),
    (
        "unquantified amount",
        re.compile(
            r"\b(?:several|various|numerous|many|most|a few|some|"
            r"a (?:number|variety|range|lot) of)\b",
            re.IGNORECASE,
        ),
        "how many, and which?",
    ),
    (
        "comparison without a baseline",
        re.compile(
            r"\b(?:better|worse|outperform(?:s|ed|ing)?|superior|inferior|"
            r"improv(?:e|es|ed|ing|ement|ements)|faster|slower|higher|lower|"
            r"more (?:accurate|efficient|robust|effective|stable|reliable)|"
            r"less (?:accurate|efficient|robust|effective|stable|reliable))\b",
            re.IGNORECASE,
        ),
        "compared with what, measured how?",
    ),
    (
        "unscoped claim",
        re.compile(
            r"\b(?:robust(?:ly|ness)?|generali[sz](?:e|es|ed|ation|ability)|"
            r"scal(?:able|ability|es well)|"
            r"efficient(?:ly)?|effective(?:ly|ness)?|reliabl[ey]|interpretab(?:le|ility)|"
            r"state[- ]of[- ]the[- ]art|general[- ]purpose|in practice|real[- ]world)\b",
            re.IGNORECASE,
        ),
        "under which conditions, on which data, against what threat or shift?",
    ),
    (
        "vague relation",
        re.compile(
            r"\b(?:related to|associated with|in terms of|plays? an? (?:key|crucial|important|"
            r"significant|central|major) role|contribut(?:es|ed|ing) to|leverag(?:e|es|ed|ing)|"
            r"address(?:es|ed|ing)?|handl(?:e|es|ed|ing)|impact(?:s|ed)?|affect(?:s|ed)?)\b",
            re.IGNORECASE,
        ),
        "what is the relation exactly: cause, correlation, or use?",
    ),
    (
        "unclear referent",
        re.compile(
            r"^(?:This|These|That|Those|It|Such)\s+(?:is|are|was|were|shows?|suggests?|means|"
            r"implies|leads?|allows?|enables?|makes?|results?|demonstrates?|indicates?|"
            r"can|may|could|would|will|has|have|helps?|reduces?|increases?|improves?)\b",
        ),
        "what does 'this'/'it' refer to?",
    ),
]

# Comparisons and magnitudes that come with a number are usually already pinned down.
_SUPPRESSED_BY_NUMBERS = frozenset(
    {"unquantified magnitude", "comparison without a baseline", "unquantified amount"}
)


@dataclass(frozen=True)
class Sentence:
    text: str
    offset: int  # character offset inside the paragraph text
    cues: tuple[str, ...] = ()
    hints: tuple[str, ...] = field(default=())


def split_sentences(text: str) -> list[tuple[str, int]]:
    """Split paragraph text into (sentence, offset) pairs, keeping LaTeX intact."""
    protected = text
    for abbreviation in _ABBREVIATIONS:
        protected = protected.replace(abbreviation, abbreviation.replace(".", "\0"))
    sentences: list[tuple[str, int]] = []
    start = 0
    for match in _SENTENCE_END_RE.finditer(protected):
        end = match.end()
        chunk = text[start:end].strip()
        if chunk:
            sentences.append(
                (chunk, start + (len(text[start:end]) - len(text[start:end].lstrip())))
            )
        start = end
    tail = text[start:].strip()
    if tail:
        sentences.append((tail, start + (len(text[start:]) - len(text[start:].lstrip()))))
    return sentences


def screen(text: str) -> list[Sentence]:
    """Return sentences with vagueness cues, each tagged with the cues it matched."""
    candidates = []
    for sentence, offset in split_sentences(text):
        prose = _INLINE_MATH_RE.sub(" ", sentence)
        if not has_prose(prose):
            continue
        has_number = bool(_NUMBER_RE.search(prose))
        matched = [
            (name, hint)
            for name, pattern, hint in _CUES
            if pattern.search(prose) and not (has_number and name in _SUPPRESSED_BY_NUMBERS)
        ]
        if matched:
            candidates.append(
                Sentence(
                    sentence,
                    offset,
                    tuple(name for name, _ in matched),
                    tuple(hint for _, hint in matched),
                )
            )
    return candidates


# --------------------------------------------------------------------------- prompts

_READ_PROMPT = """You are a careful expert reader who did NOT write this paper and \
cannot ask the author anything. Your job is to find sentences that a reasonable reader \
in this field could understand in more than one way, where the different readings would \
lead to different conclusions about what the paper claims, did, or found.

You will get one paragraph and a numbered list of candidate sentences from it, each with \
cues that flagged it. The cues are hints, not verdicts.

For each candidate, decide whether the paragraph pins down the meaning. It is NOT \
ambiguous when:
- a number, citation, definition, or the surrounding sentences fix the meaning;
- the hedge is itself precise ("may", "in our experiments", "on the datasets above");
- the readings differ only in wording, not in what a reader would believe.

When it IS ambiguous, give the shortest phrase responsible (an exact substring of the \
sentence), two to four concrete readings (each a full restatement committing to one \
meaning), and the one question the author must answer to remove the ambiguity.

Respond with a JSON object of this exact form:
{
  "findings": [
    {
      "id": 1,
      "phrase": "exact substring of that sentence",
      "readings": ["first concrete reading", "second concrete reading"],
      "question": "the question the author must answer"
    }
  ]
}
Return {"findings": []} when every candidate is clear. Most sentences in a good paper are."""

_VERIFY_PROMPT = """You are checking another reviewer's claim that a phrase in a \
scientific paragraph is ambiguous. Be skeptical: false alarms waste the author's time.

Answer two questions using only the paragraph:
1. plausible: could a careful expert reader of this paragraph genuinely hold EACH of the \
listed readings? A reading that the paragraph rules out, or that no expert would \
consider, is not plausible.
2. material: would the readings lead a reader to different conclusions about what was \
claimed, done, or found (not just different wording)?

Respond with a JSON object of this exact form:
{"plausible": true | false, "material": true | false, "reason": "one sentence"}"""


def _render_read(paragraph: str, candidates: list[Sentence]) -> str:
    lines = [f"Paragraph:\n{paragraph}\n", "Candidate sentences:"]
    for index, sentence in enumerate(candidates, start=1):
        hints = "; ".join(
            f"{cue} ({hint})" for cue, hint in zip(sentence.cues, sentence.hints, strict=True)
        )
        lines.append(f"{index}. {sentence.text}\n   cues: {hints or 'none'}")
    return "\n".join(lines)


def _render_verify(paragraph: str, phrase: str, readings: list[str]) -> str:
    listed = "\n".join(f"- {reading}" for reading in readings)
    return f"Paragraph:\n{paragraph}\n\nPhrase: {phrase}\n\nProposed readings:\n{listed}"


# --------------------------------------------------------------------------- checker


@dataclass
class _Proposal:
    paragraph: Paragraph
    sentence: Sentence
    phrase: str
    readings: list[str]
    question: str


class AmbiguityChecker:
    """Flags sentences with competing readings, showing the readings and the question."""

    name = "ambiguity"

    def __init__(
        self, llm: LLMClient, concurrency: int = 1, screen: bool = True, verify: bool = True
    ) -> None:
        self._llm = llm
        self._concurrency = concurrency
        self._screen = screen
        self._verify = verify

    def check(self, doc: Document) -> list[Finding]:
        work = [(p, self._candidates(p.text)) for p in doc.paragraphs if has_prose(p.text)]
        work = [(p, c) for p, c in work if c]
        responses = ordered_parallel_map(
            lambda item: self._llm.complete_json(_READ_PROMPT, _render_read(item[0].text, item[1])),
            work,
            self._concurrency,
        )
        proposals = [
            proposal
            for (para, candidates), response in zip(work, responses, strict=True)
            for proposal in _proposals(para, candidates, response)
        ]
        if self._verify and proposals:
            verdicts = ordered_parallel_map(
                lambda prop: self._llm.complete_json(
                    _VERIFY_PROMPT, _render_verify(prop.paragraph.text, prop.phrase, prop.readings)
                ),
                proposals,
                self._concurrency,
            )
            proposals = [p for p, v in zip(proposals, verdicts, strict=True) if _confirmed(v)]
        return [_to_finding(p, self.name) for p in proposals]

    def _candidates(self, text: str) -> list[Sentence]:
        if self._screen:
            return screen(text)
        return [
            Sentence(s, o)
            for s, o in split_sentences(text)
            if has_prose(_INLINE_MATH_RE.sub(" ", s))
        ]


def _proposals(para: Paragraph, candidates: list[Sentence], response: dict) -> Iterable[_Proposal]:
    for raw in response.get("findings", []) or []:
        if not isinstance(raw, dict):
            continue
        try:
            sentence = candidates[int(raw.get("id")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        readings = [str(r).strip() for r in raw.get("readings", []) or [] if str(r).strip()]
        if len(set(readings)) < 2:
            continue  # one reading is not an ambiguity
        phrase = str(raw.get("phrase") or "").strip()
        if not phrase or phrase not in sentence.text:
            phrase = sentence.text
        yield _Proposal(para, sentence, phrase, readings, str(raw.get("question") or "").strip())


def _confirmed(verdict: dict) -> bool:
    return verdict.get("plausible") is True and verdict.get("material") is True


def _to_finding(proposal: _Proposal, checker: str) -> Finding:
    readings = "; ".join(f"({chr(97 + i)}) {r}" for i, r in enumerate(proposal.readings))
    question = proposal.question or "Which reading do you mean?"
    return Finding(
        checker=checker,
        severity=Severity.warning,
        line=_line_of(proposal),
        message=f'"{proposal.phrase}" can be read more than one way: {readings}',
        suggestion=f"{question} Rewrite so only the intended reading fits.",
        excerpt=proposal.phrase,
        file=str(proposal.paragraph.file) if proposal.paragraph.file else None,
    )


def _line_of(proposal: _Proposal) -> int:
    para = proposal.paragraph
    within = proposal.sentence.text.find(proposal.phrase)
    offset = proposal.sentence.offset + max(within, 0)
    return para.start_line + para.text[:offset].count("\n")
