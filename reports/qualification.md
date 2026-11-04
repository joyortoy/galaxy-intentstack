# First milestone qualification

Date: 2026-11-05 (Asia/Singapore). Development and tests ran in the isolated checkout
/home/sam/galaxy-intentstack-dev-20261105 on SSH host joy. No production state was changed.
This report establishes a local vertical slice, not production readiness.

## Discovery and reuse

The target joyortoy/galaxy-intentstack repository was empty.
Read-only inspection found existing IntentStack scoped memory, provenance, revision and approval
interfaces; JoyEvidence transactional authenticated evidence; JoyCtl deterministic policy/grants
and IntentDeck quarantine; JoyMux runtime boundaries. See docs/capability-matrix.md.

Reused interfaces: IntentStack's memory id/revision/text/source_ref shape and classifier intent
shape. The optional contract test called the actual installed release classifier.
No existing implementation source was copied and no live service was connected. Memory writes,
executions and authenticated audit ownership remain in the existing systems. Unverified capabilities
are explicitly marked in the matrix. Qodo configuration was unavailable; no Qodo rules were loaded.

## New implementation and locations

- src/galaxy_intentstack/models.py: seven epistemic states and structured decisions.
- audit.py: durable SQLite state, append-only audit, commitments, replay identity and restart check.
- beliefs.py: revision, evidence retraction, source trust updates, dependency invalidation and verification.
- analysis.py: uncertain observable manipulation rules and ambiguity-preserving interpretations.
- authorization.py: independent deterministic scoped permission, approval, expiry and revocation.
- engine.py: complete transactionally persisted pipeline and local execution recheck.
- integrations.py: six local adapters; api.py: all-eight-scenario CLI demo.
- tests/{unit,integration,adversarial}, benchmarks/, examples/, docs/.

The conservative extractor emits one whole-message claim, with a narrow meeting-day semantic
slot for contradiction/revision. Unrecognized semantics are not silently treated as verified.
Graph changes only affect linked descendants; stale conclusions require explicit review/rebuild.

## Commands executed and results

```sh
.venv/bin/python -m pytest -q
PYTHONPATH=/home/sam/intentstack-production/current/IntentStack/src .venv/bin/python -m pytest -q
.venv/bin/ruff check src tests benchmarks examples
.venv/bin/ruff format --check src tests benchmarks examples
.venv/bin/python benchmarks/run.py --rounds 10
```

Core suite: **38 passed, 1 optional integration skip**.
Existing-classifier suite: **39 passed, 0 failures**.
Clean venv: installed locked dependencies, built and installed the package noneditably;
ran tests from /tmp with pytest pythonpath override cleared: **38 passed, 1 optional skip**.
Lint and formatting passed. Raw logs are reports/tests-core.txt, tests-integrated.txt,
tests-installed.txt, fresh-install.txt, lint.txt and format.txt.

All eight required scenarios passed:
1. Metaphor preserves literal/metaphorical readings without confirmed personal intention.
2. False administrator claim remains reported and cannot transfer authority.
3. Guilt pressure is uncertain behavioral evidence; absent permission denies access.
4. Trusted correction preserves Monday, activates Tuesday and stales Monday descendants.
5. Memory preapproval cannot create permissions.
6. Queued permission revoked before execution blocks the callback, including after restart.
7. Multi-turn citations retain root provenance and cannot promote verification or permission.
8. Reasoned persuasion does not itself trigger a manipulation finding; trusted correction can revise.

Additional tests cover exact action binding including belief preconditions, expiry, approval,
principal/session boundaries, retraction, source trust withdrawal, branching invalidation,
conflicting replay, identical repetitions, secret-shaped content, failed callbacks,
audit corruption at restart and one local invocation per successfully consumed queue entry.

## Measured benchmark

24 manually labeled examples repeated ten times = **240 decisions**, not 240 independent examples.
Fixture SHA256: 8c44a7415afb6958d51bf7b71782a22ef724ff1afb5066b505aa99db6f4ffe43.

| Observation | Measured |
|---|---:|
| Evidence provenance completeness | 100% |
| Unsupported VERIFIED promotion | 0% |
| Unauthorized ALLOW on denied fixture actions | 0% |
| Audit completeness | 100% |
| Detector precision | 76.92% |
| Detector recall | 83.33% |
| Benign false-positive rate | 25% |
| Median local decision latency | 0.294 ms |
| p95 local decision latency | 0.417 ms |
| Maximum observed decision latency | 1.035 ms |

Revision, downstream invalidation, restart recovery and audit-chain checks passed.
A separately granted legitimate action returned ALLOW, checking that the gate does not simply
deny everything. These observations are not a false-authorization probability bound.
Timing is specific to Linux/Python 3.13.7 and this tiny local dataset; there is no production SLA.

The detector misses the veiled-threat and indirect-urgency fixtures. It flags benign quotation,
citation and urgency fixtures. These are measured detector failures, although all required
acceptance scenarios and policy tests pass. reports/benchmark.json contains targets separately
from measured observations.

## Demonstration artifacts

reports/demo.jsonl has 13 inspectable records covering all eight scenarios and a graph snapshot.
reports/demo-qualified.db contains the corresponding local durable state.
The demonstration was run from the clean installed package and inspected programmatically:
queued ALLOW, post-revocation denial, all multi-turn action denials and valid audit chain.
The earlier development-only reports/demo.db is not the qualified demonstration.

Reproduce from a fresh checkout on host joy:
```sh
cd /home/sam/galaxy-intentstack-dev-20261105
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pytest -q
.venv/bin/galaxy-demo --db /tmp/galaxy-reproduce-new.db > /tmp/galaxy-reproduce.jsonl
.venv/bin/python benchmarks/run.py --rounds 10 > /tmp/galaxy-reproduce-benchmark.json
```
Choose a database path that does not already exist.

## Security limitations and readiness

Ready for local library evaluation and an isolated adapter trial. Not ready for production
consequential actions. In particular:
- Rule-based semantic coverage is narrow and the benign detector false-positive rate is high.
- Source identity/session authentication and approval-risk selection are host responsibilities.
- The audit is an unkeyed local chain, weaker than JoyEvidence. No external retained head or
  protected projection reconstruction prevents a database owner from rewriting history.
- Secret filtering is heuristic; the host must exclude secrets and protect private evidence.
- No live JoyCtl grant verification, IntentStack transport authentication or JoyEvidence delivery.
- The callback boundary is for bounded local tests. No exactly-once remote effects, crash-after-effect
  reconciliation or distributed cancellation. Previously returned ALLOW decisions are historical.
- One local database is one trusted tenant; service-level quotas and tenant authentication remain work.

## Next engineering milestone

Implement an isolated, read-only IntentStack client plus a real JoyCtl execution-grant verifier,
bind host identity/session/action/revision proofs, and deliver audit commitments through the
existing JoyEvidence outbox/ledger. Add independent review and crash/race qualification before
enabling any external execution. No production deployment or GitHub push was performed.
