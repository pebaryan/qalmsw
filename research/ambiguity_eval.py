"""Measure the ambiguity checker against a real LLM on the paired benchmark.

Each pair in ``tests/fixtures/ambiguity_pairs.json`` is the same claim written vaguely
and precisely. A good checker flags the vague version and leaves the precise one alone:

    python -m research.ambiguity_eval                       # uses QALMSW_BASE_URL / QALMSW_MODEL
    python -m research.ambiguity_eval --no-screen           # send every sentence to the LLM
    python -m research.ambiguity_eval --no-verify --json    # skip the verification pass

Reports recall (vague pairs flagged), false-alarm rate (precise pairs flagged), and the
pairs each pass gets wrong.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qalmsw.checkers.ambiguity import AmbiguityChecker
from qalmsw.document import Document
from qalmsw.llm import LlamaCppClient
from qalmsw.parse import Paragraph

PAIRS_PATH = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "ambiguity_pairs.json"


def _flagged(checker: AmbiguityChecker, text: str) -> list[str]:
    doc = Document(path=Path("pair.tex"), source=text, paragraphs=[Paragraph(text, 1, 1)])
    return [f.message for f in checker.check(doc)]


def evaluate(checker: AmbiguityChecker, pairs: list[dict]) -> dict:
    rows = []
    for pair in pairs:
        rows.append(
            {
                "id": pair["id"],
                "vague_flagged": _flagged(checker, pair["vague"]),
                "precise_flagged": _flagged(checker, pair["precise"]),
            }
        )
    total = len(rows) or 1
    return {
        "pairs": len(rows),
        "recall": sum(bool(r["vague_flagged"]) for r in rows) / total,
        "false_alarm_rate": sum(bool(r["precise_flagged"]) for r in rows) / total,
        "missed": [r["id"] for r in rows if not r["vague_flagged"]],
        "false_alarms": [r["id"] for r in rows if r["precise_flagged"]],
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--no-screen", action="store_true", help="send every sentence to the LLM")
    parser.add_argument("--no-verify", action="store_true", help="skip the verification pass")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()

    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"]
    llm = LlamaCppClient(base_url=args.base_url, model=args.model)
    checker = AmbiguityChecker(llm, screen=not args.no_screen, verify=not args.no_verify)
    result = evaluate(checker, pairs)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"pairs:            {result['pairs']}")
    print(f"recall:           {result['recall']:.0%}  (vague versions flagged)")
    print(f"false-alarm rate: {result['false_alarm_rate']:.0%}  (precise versions flagged)")
    if result["missed"]:
        print("missed:           " + ", ".join(result["missed"]))
    if result["false_alarms"]:
        print("false alarms:     " + ", ".join(result["false_alarms"]))


if __name__ == "__main__":
    main()
