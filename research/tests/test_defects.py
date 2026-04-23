import random

from research.corpus import BaseTriple
from research.defects import apply_operators, identity, swap_random, truncate_head


def _triple(arxiv_id: str, abstract: str = "First sentence. Second sentence.") -> BaseTriple:
    return BaseTriple(
        paper_id="test/0001",
        cite_key=f"key_{arxiv_id}",
        cited_arxiv_id=arxiv_id,
        paragraph_text=f"A claim attributed to {arxiv_id}.",
        paragraph_line=1,
        abstract=abstract,
        cited_title=f"Title {arxiv_id}",
    )


def test_identity_preserves_abstract_and_labels_supports():
    base = _triple("2301.00001")
    out = identity(base)
    assert out.abstract == base.abstract
    assert out.label == "supports"
    assert out.operator == "identity"


def test_swap_random_replaces_abstract_and_labels_unrelated():
    base = _triple("2301.00001", "Original abstract.")
    donor = _triple("2301.99999", "Donor abstract from unrelated paper.")
    rng = random.Random(0)
    out = swap_random(base, [base, donor], rng)
    assert out is not None
    assert out.abstract == donor.abstract
    assert out.label == "unrelated"
    assert "2301.99999" in out.notes


def test_swap_random_returns_none_when_no_donors():
    base = _triple("2301.00001")
    rng = random.Random(0)
    assert swap_random(base, [base], rng) is None


def test_truncate_head_keeps_only_first_sentence():
    base = _triple("2301.00001", "First. Second. Third.")
    out = truncate_head(base)
    assert out.abstract.rstrip(".").strip() == "First"
    assert out.label == "unclear"
    assert out.operator == "truncate_head"


def test_truncate_head_handles_short_abstracts():
    base = _triple("2301.00001", "Only one.")
    out = truncate_head(base)
    # No-op for single-sentence abstracts — we still produce the entry; label
    # mismatch will be caught by the primary-author spot-check per PLAN.md.
    assert out.abstract != ""
    assert out.operator == "truncate_head"


def test_apply_operators_produces_one_per_base_per_op():
    bases = [_triple(f"2301.{i:05d}") for i in range(1, 4)]
    out = apply_operators(bases, seed=42)
    ops = [d.operator for d in out]
    # identity + truncate_head always fire; swap_random needs a donor (always available
    # here) so we expect 3 per base.
    assert ops.count("identity") == 3
    assert ops.count("truncate_head") == 3
    assert ops.count("swap_random") == 3


def test_apply_operators_is_deterministic_under_fixed_seed():
    bases = [_triple(f"2301.{i:05d}") for i in range(1, 6)]
    a = apply_operators(bases, seed=123)
    b = apply_operators(bases, seed=123)
    assert [d.notes for d in a] == [d.notes for d in b]
