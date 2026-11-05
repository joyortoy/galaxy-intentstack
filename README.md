# Galaxy IntentStack

A working local integrity layer for AI agents: durable evidence, conservative interpretation,
dependency-aware belief revision and deterministic authorization. No model API is required.

## Current status

The isolated local-development integration is implemented and tested. **169 tests pass** across
core policy, real ecosystem integration, dependency revocation, guarded startup and eight
hard-process-exit recovery cases. Production qualification and physical attestation remain
unestablished. The language detector is a small rule set, not a general truth oracle or a
psychological assessment tool.

| Validation mode | What runs | Measured time on joy | Test storage |
| --- | --- | --- | --- |
| Routine quick check | All 169 tests, lint, formatting, benchmarks and independent audit checks | 17.44 seconds total | Temporary, memory-backed on joy |
| Full qualification | Same checks with persistent test storage | 177.50 seconds for tests | Checkout work directory on disk |

Measurements are from 2026-11-05 on Linux / Python 3.13.7. Quick mode does not qualify durable
storage or power-loss behavior. See [full qualification](reports/startup-guard/qualification.md)
and [quick-check evidence](reports/quick-check/qualification.md).

## How it works

1. **Collect evidence.** IntentStack supplies source records and memories. Galaxy tracks their
   provenance, uncertainty, contradictions and belief dependencies.
2. **Evaluate an action.** Deterministic policy returns ALLOW, DENY, CLARIFY, ABSTAIN or ESCALATE.
   Confidence and retrieved text cannot create execution authority.
3. **Authorize and execute.** JoyCtl independently validates its native grant and admitted compiled
   plan. JoyMux handles runtime placement through Unix sockets.
4. **Invalidate stale support.** Retraction, dispute or correction blocks dependent authority and
   creates durable revocation work for JoyCtl. Pending forwarding still blocks affected leases.
5. **Verify and audit.** JoyCtl retains custody facts and verifies execution; JoyEvidence supplies
   the authenticated audit trail. Command success does not establish semantic acceptance,
   independent human review or physical attestation.

The guarded host starts closed. Queueing, worker claims and verification recovery require healthy
dependency and audit composition. Health failures latch it closed; a fresh successful bootstrap is
required. Healthy draining retains in-flight custody evidence for later verification.

## Run the ecosystem checks

On the existing host joy:

```sh
cd /home/sam/galaxy-intentstack-startup-20261105
# Routine feedback, about 17 seconds in the recorded run:
.venv-phase2/bin/python scripts/qualify_phase2.py --quick

# Persistent-storage qualification, about three minutes in the recorded run:
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/startup-guard
```

Both modes print progress and elapsed time. Quick results default to reports/quick-check;
full results use the directory specified above. For a new environment, follow the
[ecosystem setup and requirements](docs/phase2-reproduction.md) and
[guarded startup instructions](docs/startup-guard.md). The separate upstream repositories,
Linux sandbox tools and a built JoyLang kernel are required for ecosystem qualification.
The standalone core setup is documented below.

## Guarded-startup follow-up

The isolated host now starts closed and gates native queueing, worker claims and verification
recovery on healthy dependency and authenticated audit composition. Health failures latch closed;
healthy draining retains custody facts for fresh-host recovery. See [design and reproduction](docs/startup-guard.md)
and [qualification](reports/startup-guard/qualification.md). For faster routine feedback on joy,
use `.venv-phase2/bin/python scripts/qualify_phase2.py --quick`; this runs all tests using temporary
storage and saves separate reports/quick-check evidence. Keep the default full run for persistent
storage qualification. Production startup/deployment,
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
The source and recorded evidence are published on GitHub. No production deployment has been performed.

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
