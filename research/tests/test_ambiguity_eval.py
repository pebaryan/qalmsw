from qalmsw.checkers.ambiguity import AmbiguityChecker
from research.ambiguity_eval import PAIRS_PATH, evaluate


class FlagVague:
    """Fake LLM that flags the first candidate only in the vague version of each pair."""

    def __init__(self, vague: set[str]) -> None:
        self.vague = vague

    def complete_json(self, system: str, user: str) -> dict:
        if "skeptical" in system:
            return {"plausible": True, "material": True}
        if any(text in user for text in self.vague):
            return {"findings": [{"id": 1, "phrase": "", "readings": ["a", "b"], "question": "q"}]}
        return {"findings": []}


def test_evaluate_scores_recall_and_false_alarms() -> None:
    import json

    pairs = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))["pairs"][:4]
    result = evaluate(
        AmbiguityChecker(FlagVague({p["vague"] for p in pairs[:3]}), screen=False), pairs
    )
    assert result["pairs"] == 4
    assert result["recall"] == 0.75
    assert result["false_alarm_rate"] == 0.0
    assert result["missed"] == [pairs[3]["id"]]
