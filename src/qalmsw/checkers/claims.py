"""Claim-to-reference verification.

Pipeline for each paragraph that contains a ``\\cite{}``:

1. Extract ``{claim, cite_keys}`` pairs via one LLM call.
2. For each ``(claim, cite_key)``:
   a. Resolve ``cite_key`` to a title via the supplied ``BibEntry`` list.
   b. Fetch the paper's abstract (Google Scholar by default; cached per bib key so we
      hit the network once per reference per run).
   c. Ask the LLM to judge whether the abstract supports the claim.
3. Emit a ``Finding`` for any non-supporting verdict (contradicts / unrelated /
   unclear) or setup failure (missing title, abstract, etc.). ``supports`` verdicts
   are silent — only problems are reported.

Design notes:
- Scholar is injected as a ``Callable[[str], ScholarResult | None]`` so tests can stub
  it without hitting the network. Default: :func:`qalmsw.retrieval.search_by_title`.
- Scholar lookups are per-run-cached by bib key. Duplicate ``\\cite`` of the same paper
  costs one network call, not N.
- We never raise on Scholar failures — they become ``info`` findings so the rest of
  the check keeps going.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qalmsw.bib import BibEntry
from qalmsw.checkers.base import Finding, Severity
from qalmsw.document import Document
from qalmsw.llm import LLMClient
from qalmsw.parse import Paragraph, scan_citations
from qalmsw.retrieval import ScholarResult, search_by_title

_EXTRACT_SYSTEM_PROMPT = """You are extracting citation-backed claims from a paragraph of a scientific paper.

A "claim" is a factual or empirical assertion that is explicitly attributed to one or \
more citations. Do NOT include statements that don't carry a citation.

You will be given:
- The paragraph text (LaTeX).
- The list of cite keys that appear in the paragraph.

For each claim, return the claim's text (paraphrased in plain English, no LaTeX) and \
the subset of cite keys the paragraph attributes it to.

Respond with a JSON object of this exact form:
{
  "claims": [
    {"claim": "plain-English claim text", "cite_keys": ["key1", "key2"]}
  ]
}

If there are no citation-backed claims, return {"claims": []}.
"""

_JUDGE_SYSTEM_PROMPT = """You are checking whether an abstract supports a claim.

You will be given:
- A claim from a scientific paper.
- The title and abstract of the paper being cited to support that claim.

Return one of four verdicts:
- "supports": the abstract clearly supports the claim.
- "contradicts": the abstract explicitly disagrees with the claim.
- "unrelated": the abstract is about a different topic and doesn't bear on the claim.
- "unclear": the abstract doesn't contain enough information either way.

Respond with a JSON object of this exact form:
{
  "verdict": "supports" | "contradicts" | "unrelated" | "unclear",
  "rationale": "one sentence explaining your judgment"
}
"""


SearchFn = Callable[[str], ScholarResult | None]


class ClaimsChecker:
    name = "claims"

    def __init__(
        self,
        llm: LLMClient,
        bib_entries: list[BibEntry],
        search: SearchFn = search_by_title,
    ) -> None:
        self._llm = llm
        self._bib_by_key = {e.key: e for e in bib_entries}
        self._search = search
        self._abstract_cache: dict[str, ScholarResult | None] = {}

    def check(self, doc: Document) -> list[Finding]:
        findings: list[Finding] = []
        for para in doc.paragraphs:
            keys = [c.key for c in scan_citations(para.text)]
            if not keys:
                continue
            claims = self._extract_claims(para, keys)
            for claim in claims:
                findings.extend(self._verify_claim(para, claim))
        return findings

    def _extract_claims(self, para: Paragraph, cite_keys: list[str]) -> list[dict[str, Any]]:
        prompt = f"Cite keys present: {', '.join(sorted(set(cite_keys)))}\n\nParagraph:\n{para.text}"
        result = self._llm.complete_json(_EXTRACT_SYSTEM_PROMPT, prompt)
        raw_claims = result.get("claims", [])
        return [c for c in raw_claims if isinstance(c, dict) and c.get("claim")]

    def _verify_claim(self, para: Paragraph, claim: dict[str, Any]) -> list[Finding]:
        claim_text = str(claim.get("claim", "")).strip()
        cite_keys = [str(k).strip() for k in claim.get("cite_keys", []) if str(k).strip()]
        findings: list[Finding] = []
        for key in cite_keys:
            findings.extend(self._verify_single(para, claim_text, key))
        return findings

    def _verify_single(self, para: Paragraph, claim_text: str, cite_key: str) -> list[Finding]:
        entry = self._bib_by_key.get(cite_key)
        if entry is None:
            return [_finding(para, Severity.info, f"Unknown cite key '{cite_key}' in claim: {claim_text}")]
        if not entry.title:
            return [
                _finding(
                    para,
                    Severity.info,
                    f"No title in bib for '{cite_key}' — cannot verify claim: {claim_text}",
                )
            ]
        abstract_result = self._lookup_abstract(cite_key, entry.title)
        if abstract_result is None:
            return [
                _finding(
                    para,
                    Severity.info,
                    f"Could not retrieve abstract for '{cite_key}' ({entry.title!r}) — claim unverified.",
                )
            ]
        if not abstract_result.abstract:
            return [
                _finding(
                    para,
                    Severity.info,
                    f"Retrieved record for '{cite_key}' has no abstract — claim unverified.",
                )
            ]
        verdict_raw = self._llm.complete_json(
            _JUDGE_SYSTEM_PROMPT,
            f"Claim: {claim_text}\n\nCited paper title: {abstract_result.title}\n\nAbstract: {abstract_result.abstract}",
        )
        verdict = str(verdict_raw.get("verdict", "unclear")).strip().lower()
        rationale = str(verdict_raw.get("rationale", "")).strip()
        if verdict == "supports":
            return []
        severity = Severity.error if verdict == "contradicts" else Severity.warning
        message = f"[{verdict}] claim '{claim_text}' vs {cite_key}: {rationale}"
        return [_finding(para, severity, message)]

    def _lookup_abstract(self, cite_key: str, title: str) -> ScholarResult | None:
        if cite_key in self._abstract_cache:
            return self._abstract_cache[cite_key]
        try:
            result = self._search(title)
        except Exception:
            result = None
        self._abstract_cache[cite_key] = result
        return result


def _finding(para: Paragraph, severity: Severity, message: str) -> Finding:
    return Finding(
        checker="claims",
        severity=severity,
        line=para.start_line,
        message=message,
        file=str(para.file) if para.file else None,
    )
