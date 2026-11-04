"""Manually labeled, frozen development/held-out fixture evaluation; not a population estimate."""
import argparse
import hashlib
import json
from pathlib import Path

from galaxy_intentstack.analysis import assess


def evaluate(split):
    raw = Path(__file__).with_name("detector-" + split + ".json").read_bytes()
    items = json.loads(raw)
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    errors = []
    for item in items:
        prediction = bool(assess(item["text"], "fixture:" + item["id"], item["source_type"]))
        key = ("tp" if prediction else "fn") if item["attack"] else ("fp" if prediction else "tn")
        counts[key] += 1
        if key in ("fp", "fn"):
            errors.append({"id": item["id"], "category": item["category"], "error": key})
    attacks = counts["tp"] + counts["fn"]
    benign = counts["fp"] + counts["tn"]
    return {"split": split, "fixture_sha256": hashlib.sha256(raw).hexdigest(),
            "cases": len(items), "attack_denominator": attacks, "benign_denominator": benign,
            "predicted_positive_denominator": counts["tp"] + counts["fp"],
            "confusion_matrix": counts,
            "precision": counts["tp"]/(counts["tp"]+counts["fp"]) if counts["tp"]+counts["fp"] else None,
            "recall": counts["tp"]/attacks, "false_positive_rate": counts["fp"]/benign,
            "false_negative_rate": counts["fn"]/attacks, "errors": errors,
            "limitations": "Author-written labels; no independent annotator or statistical claim"}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["development", "heldout"], required=True)
    print(json.dumps(evaluate(p.parse_args().split), indent=2, sort_keys=True))
