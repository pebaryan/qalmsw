"""Defect operators — turn a ``BaseTriple`` into a labeled ``DefectedTriple``.

Each operator takes a ``BaseTriple`` (+ state the operator needs, e.g. a pool of other
abstracts for ``swap_random``) and returns a ``DefectedTriple`` whose ``label`` is the
ground-truth verdict a correct judge should produce. Labels match qalmsw's
:class:`qalmsw.checkers.claims` verdict set.

Covered in this first pass:

- ``identity`` → ``supports`` (the paragraph's own cited abstract; base assumption).
- ``swap_random`` → ``unrelated`` (replace abstract with one drawn from the pool).
- ``truncate_head`` → ``unclear`` (keep only the first sentence of the real abstract).

Remaining operators from PLAN.md (``swap_near``, ``claim_negate``, ``claim_strengthen``)
are left as follow-up work — they need either an embedding model or a frontier-LLM
dependency, both of which are bigger commitments than this scaffold warrants.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Literal

from research.corpus import BaseTriple

Label = Literal["supports", "contradicts", "unrelated", "unclear"]
OperatorName = Literal[
    "identity", "swap_random", "swap_near", "truncate_head", "claim_negate", "claim_strengthen"
]


@dataclass(frozen=True)
class DefectedTriple:
    base: BaseTriple
    abstract: str  # possibly-perturbed; callers use this, not base.abstract
    paragraph_text: str  # possibly-perturbed
    label: Label
    operator: OperatorName
    notes: str = ""


def identity(triple: BaseTriple) -> DefectedTriple:
    return DefectedTriple(
        base=triple,
        abstract=triple.abstract,
        paragraph_text=triple.paragraph_text,
        label="supports",
        operator="identity",
    )


def swap_random(
    triple: BaseTriple,
    pool: list[BaseTriple],
    rng: random.Random,
) -> DefectedTriple | None:
    """Replace the abstract with one drawn uniformly from ``pool`` (excluding self).

    Returns None if the pool contains no viable alternative — callers should treat
    that as "skip this base triple for this operator" rather than an error.
    """
    candidates = [
        t for t in pool
        if t.cited_arxiv_id != triple.cited_arxiv_id and t.abstract
    ]
    if not candidates:
        return None
    donor = rng.choice(candidates)
    return DefectedTriple(
        base=triple,
        abstract=donor.abstract,
        paragraph_text=triple.paragraph_text,
        label="unrelated",
        operator="swap_random",
        notes=f"donor_arxiv_id={donor.cited_arxiv_id}",
    )


_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


def truncate_head(triple: BaseTriple, *, sentences: int = 1) -> DefectedTriple:
    """Keep only the first ``sentences`` sentences of the abstract."""
    parts = _SENTENCE_END_RE.split(triple.abstract)
    kept = " ".join(parts[:sentences]).strip()
    # If the abstract was already short enough that truncation is a no-op, the
    # ground-truth label is probably still the original — caller can filter those
    # out by comparing lengths. We tag as `unclear` regardless; the primary
    # author's spot-check will catch no-op cases.
    return DefectedTriple(
        base=triple,
        abstract=kept or triple.abstract,
        paragraph_text=triple.paragraph_text,
        label="unclear",
        operator="truncate_head",
        notes=f"kept_sentences={sentences}",
    )


def apply_operators(
    base: list[BaseTriple],
    *,
    seed: int = 0,
    identity_rate: float = 1.0,
    swap_random_rate: float = 1.0,
    truncate_head_rate: float = 1.0,
) -> list[DefectedTriple]:
    """Generate a labeled set from a base corpus.

    For each base triple we emit up to three variants — one per enabled operator —
    with inclusion gated by the per-operator rate. ``seed`` makes the sampling
    deterministic.
    """
    rng = random.Random(seed)
    out: list[DefectedTriple] = []
    for triple in base:
        if rng.random() < identity_rate:
            out.append(identity(triple))
        if rng.random() < swap_random_rate:
            result = swap_random(triple, base, rng)
            if result is not None:
                out.append(result)
        if rng.random() < truncate_head_rate:
            out.append(truncate_head(triple))
    return out
