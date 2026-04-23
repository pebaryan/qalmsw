"""Ad-hoc smoke test — not a unit test. Hits the network. Run manually."""
from __future__ import annotations

import sys

import research.arxiv as arxiv_mod
from research.arxiv import fetch_metadata, fetch_source
from research.corpus import sample_triples_from_paper
from research.defects import apply_operators

arxiv_mod.SLEEP_BETWEEN_REQUESTS = 1.5


def main(paper_id: str = "1706.03762") -> None:
    src = fetch_source(paper_id)
    print(f"[arxiv] fetched {len(src)} .tex files from {paper_id}")

    main_files = [(n, t) for n, t in src.items() if "\\begin{document}" in t]
    if not main_files:
        # Fall back: maybe everything is a fragment — synthesize a wrapper around the
        # shortest-named file so qalmsw's parser has a body to work with.
        if not src:
            print("[arxiv] no .tex content — aborting")
            sys.exit(1)
        name = sorted(src, key=len)[0]
        print(
            f"[arxiv] no file contains \\begin{{document}}; wrapping {name} "
            f"as a synthetic body"
        )
        wrapped = (
            "\\documentclass{article}\n\\begin{document}\n"
            + src[name]
            + "\n\\end{document}\n"
        )
        src = {name: wrapped}
    else:
        print(f"[arxiv] main doc file: {main_files[0][0]}")

    triples = sample_triples_from_paper(
        paper_id, src, bib_text=None, max_per_paper=3, sleep_between=1.5
    )
    print(f"[corpus] produced {len(triples)} base triples")
    for t in triples:
        print(f"  cite={t.cite_key:20s} -> arxiv:{t.cited_arxiv_id}")
        print(f"    paragraph (first 120c): {t.paragraph_text[:120]!r}")
        print(f"    abstract  (first 120c): {t.abstract[:120]!r}")

    if not triples:
        print("[corpus] no triples — skipping defects")
        return

    variants = apply_operators(triples, seed=0)
    print(f"[defects] generated {len(variants)} labeled variants")
    for v in variants[:6]:
        print(f"  op={v.operator:14s} label={v.label:11s} abs={v.abstract[:80]!r}")


if __name__ == "__main__":
    pid = sys.argv[1] if len(sys.argv) > 1 else "1706.03762"
    meta = fetch_metadata(pid)
    print(f"[arxiv] {pid}: {meta.title if meta else 'UNKNOWN'}")
    main(pid)
