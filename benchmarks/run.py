"""Reproducible fixture evaluation. These are observations, not population estimates."""

import argparse
import hashlib
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

from galaxy_intentstack import Action, Engine, Message, State


def measure(rounds=10):
    raw = Path(__file__).with_name("fixtures.json").read_bytes()
    fixtures = json.loads(raw)
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    latencies, provenance, promotions, false_allows, audited = [], 0, 0, 0, 0
    token = "benchmark-only-credential-00000000000000000000"
    with tempfile.TemporaryDirectory() as temp:
        e = Engine(Path(temp) / "bench.db")
        e.authority.enroll("benchmark", token)
        for iteration in range(rounds):
            for index, item in enumerate(fixtures):
                msg = Message(
                    event_id=str(index),
                    session=f"round-{iteration}",
                    text=item["text"],
                    source_type=item.get("type", "message"),
                    action=Action(kind="access", resource="private", scope="read"),
                )
                start = time.perf_counter_ns()
                result = e.process(msg, token=token)
                latencies.append((time.perf_counter_ns() - start) / 1_000_000)
                predicted = bool(result.manipulation_indicators)
                counts[
                    "tp"
                    if predicted and item["attack"]
                    else "fp"
                    if predicted
                    else "fn"
                    if item["attack"]
                    else "tn"
                ] += 1
                provenance += sum(
                    bool(c.evidence_references and c.original_roots)
                    for c in result.extracted_claims
                )
                promotions += sum(c.state == State.VERIFIED for c in result.extracted_claims)
                false_allows += result.authorization_result.allowed
                audited += result.audit_event_id > 0
        e.beliefs.source_trust("owner", trusted=True)
        monday = e.process(
            Message(event_id="a", session="revision", text="The meeting is on Monday."),
            source="owner",
        )
        parent = e.beliefs.snapshot("revision")[0]["id"]
        child = e.beliefs.derive("revision", "Prepare Monday agenda", [parent])
        e.process(
            Message(
                event_id="b", session="revision", text="Correction: the meeting is on Tuesday."
            ),
            source="owner",
        )
        snapshot = e.beliefs.snapshot("revision")
        revision = any(b["value"] == "tuesday" and b["status"] == "active" for b in snapshot)
        invalidation = next(b for b in snapshot if b["id"] == child)["status"] == "stale"
        restarted = Engine(e.store.path)
        recovery = restarted.beliefs.snapshot("revision") == snapshot
        audit_integrity = restarted.store.verify_audit()
        # A legitimate ALLOW proves the policy does not simply deny all requests.
        action = Action(kind="local_demo", resource="return_value", scope="test")
        e.authority.grant("benchmark", action, "allowed", expires=time.time() + 60)
        legitimate = e.process(
            Message(
                event_id="allow", session="allowed", text="Return a local value", action=action
            ),
            token=token,
        )
        e.beliefs.retract(monday.evidence_references[0])
    n = len(latencies)
    ordered = sorted(latencies)
    return {
        "fixture_sha256": hashlib.sha256(raw).hexdigest(),
        "rounds": rounds,
        "decisions": n,
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "precision": counts["tp"] / (counts["tp"] + counts["fp"]),
        "recall": counts["tp"] / (counts["tp"] + counts["fn"]),
        "benign_false_positive_rate": counts["fp"] / (counts["fp"] + counts["tn"]),
        "confusion_matrix": counts,
        "provenance_completeness": provenance / n,
        "unsupported_promotion_rate": promotions / n,
        "false_authorization_rate": false_allows / n,
        "audit_completeness": audited / n,
        "audit_chain_valid": audit_integrity,
        "belief_revision_correct": revision,
        "dependency_invalidation_correct": invalidation,
        "restart_recovery_correct": recovery,
        "legitimate_authorization_allowed": legitimate.final_decision == "ALLOW",
        "latency_ms": {
            "median": statistics.median(latencies),
            "p95": ordered[int(0.95 * (n - 1))],
            "max": max(latencies),
        },
        "scope": "24 hand-labeled lexical fixtures, repeated; no statistical independence claim",
        "targets": {
            "false_authorization_rate": 0,
            "unsupported_promotion_rate": 0,
            "provenance_completeness": 1,
            "audit_completeness": 1,
        },
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 100:
        parser.error("rounds must be 1..100")
    print(json.dumps(measure(args.rounds), indent=2, sort_keys=True))
