# Galaxy IntentStack

A working local integrity layer for AI agents: durable evidence, conservative interpretation,
dependency-aware belief revision and deterministic authorization. No model API is required.

**Milestone:** local vertical slice, not production certified. The language detector is a small
rule set; it is not a general truth oracle or a psychological assessment tool.

## Guarded-startup follow-up

The isolated host now starts closed and gates native queueing, worker claims and verification
recovery on healthy dependency and authenticated audit composition. Health failures latch closed;
healthy draining retains custody facts for fresh-host recovery. See [design and reproduction](docs/startup-guard.md)
and [qualification](reports/startup-guard/qualification.md). Production startup/deployment,
identity and physical attestation remain unqualified.

## Dependency-revocation follow-up

The isolated controller now checks committed belief dependencies at native grant-validation
boundaries and durably forwards invalidation to JoyCtl's existing revocation API. Pending
forwarding does not permit a worker lease. See [design and reproduction](docs/dependency-revocation.md)
and [qualification](reports/dependency-revocation/qualification.md).
Production bootstrap, distributed cancellation, identity and physical-attestation gaps remain.

## Compiled-plan follow-up

The follow-up replaces raw instruction queueing with pinned compiled prompts linked to the
admitted JoyCtl plan. Tenant-scoped prompt reads, prompt tampering checks and real JoyLang
semantic-contract admission are exercised without granting semantic completion or physical
attestation. See [details and reproduction](docs/compiled-plan.md) and
[qualification](reports/compiled-plan/qualification.md).

## Phase 2 integration

The isolated read-only integration now uses real IntentStack retrieval, JoyCtl native grants and
queue consumption, a private real JoyMux Unix daemon, JoyCtl custody/Linux sandbox verification,
and JoyEvidence HMAC delivery. Production mode and missing physical attestation fail closed.
See [Phase 2 qualification](reports/phase2/qualification.md),
[architecture](docs/phase2-architecture.md) and [exact reproduction commands](docs/phase2-reproduction.md).
No production deployment or GitHub push is authorized or performed.

## Install and verify

Python 3.11+ (qualified on Linux / Python 3.13.7):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install -e . --no-deps
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests benchmarks
.venv/bin/ruff format --check src tests benchmarks
```

The optional real IntentStack classifier contract test skips if that separate package is absent.
All eight required scenarios and core security tests work offline after dependencies are installed.
The lock file pins the dependencies used for qualification; it is not a cross-platform wheel lock.

## Reproduce the demonstration

Choose a new database path on every run:

```sh
.venv/bin/galaxy-demo --db /tmp/galaxy-demo-fresh.db > /tmp/galaxy-decisions.jsonl
.venv/bin/python benchmarks/run.py --rounds 10 > /tmp/galaxy-benchmark.json
```

The demo covers all eight scenarios, including a queued ALLOW followed by revocation and a blocked
local execution. Inspect JSON lines, the graph snapshot, and the SQLite database. A previous
decision is historical evidence, not an execution token.

## Library use

```python
from galaxy_intentstack import Engine, Message

engine = Engine("integrity.db")
decision = engine.process(Message(
    event_id="message-1",
    session="authenticated-host-assigned-session",
    text="Every galaxy began as something too small to notice.",
))
print(decision.model_dump_json(indent=2))
```

Results include claims with epistemic state, source and root provenance, candidate interpretations,
uncertain manipulation indicators, contradictions, an independent authorization result, decision,
explanation and audit ID. ALLOW, DENY, CLARIFY, ABSTAIN and ESCALATE are distinct outcomes.

Only trusted host code may enroll identities, configure source trust, grant permissions, verify
claims or approve actions. Do not expose those methods as content-driven tools. A grant binds the
complete typed action (including belief conditions), principal, resource, scope, session and expiry.
Independent approval is enforced when the operator marks a grant as requiring approval.

## Existing system boundaries

IntentStack remains canonical memory. JoyCtl remains the execution-grant authority. JoyMux remains
the runtime; use hooks / Unix sockets, never JoyMux MCP. Galaxy's ALLOW is an additional local gate,
not a substitute for these systems' policies or grants. No production services or databases were
changed and no upstream proprietary code was copied.

See [discovery matrix](docs/capability-matrix.md), [architecture](docs/architecture.md),
[security invariants](docs/security-invariants.md), [threat model](docs/threat-model.md),
[integration](docs/integration.md), and [qualification results](reports/qualification.md).

## Phase 1 baseline measurements

The initial Phase 1 benchmark used 24 hand-labeled examples repeated ten times. It measures fixture behavior,
not real-world prevalence or independent samples. Precision is 76.9%, recall 83.3%, and benign
false-positive rate 25%. Authorization is independent of these detector scores.
See reports/benchmark.json for actual timing and invariant observations.

Phase 2 results and remaining production blockers are documented in reports/phase2/qualification.md.
The Phase 1 callback executor remains a local compatibility/test API; use the new controller
adapter for isolated ecosystem evaluation. No consequential production effects are enabled.
