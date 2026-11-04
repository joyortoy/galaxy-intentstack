# Integration contract

This document describes the Phase 1 compatibility layer. For the implemented Phase 2 real
integration and current boundaries, see [Phase 2 architecture](phase2-architecture.md).

Existing ownership remains unchanged: IntentStack canonical memory and scoped retrieval,
IntentDeck quarantine/promotion, JoyCtl PolicyDecision/ExecutionGrant, JoyMux runtime,
JoyEvidence authenticated evidence. Galaxy stores only its local advisory evidence/graph.

Adapters are pure local operations:
- incoming_message: bounded Message from a host-selected session/event ID.
- memory_result: IntentStack id, revision, text and source_ref; namespaced event ID includes
  store/memory/revision. Upstream source_ref stays on Claim. Even confirmed memory remains REPORTED.
- classifier_output: existing {intent, method, memory_write_suggested} classifier shape becomes
  INFERRED. Supplied confirmation/permission fields grant nothing.
- agent_action: strict Action validation, including required belief IDs.
- policy_authorization: evaluate the local test authority without changing it.
- audit_events: bounded append-event export for a trusted ingestion bridge.

The adapters do not connect live services, import proprietary code, authenticate a remote memory
server, or verify JoyCtl signatures. No audit delivery or JoyEvidence ingestion is claimed.
Real existing classifier contract smoke:
```sh
PYTHONPATH=/home/sam/intentstack-production/current/IntentStack/src \
  .venv/bin/python -m pytest tests/integration/test_adapters.py -q
```

## Trusted-host example

```python
import secrets
import time
from galaxy_intentstack import Action, Engine, Message

engine = Engine("local-test.db")
credential = secrets.token_urlsafe(32)  # trusted host only; never log it
engine.authority.enroll("local-user", credential)
action = Action(kind="return_value", resource="local-demo", scope="test")
grant_id = engine.authority.grant(
    "local-user", action, "host-session", expires=time.time() + 60)
decision = engine.process(
    Message(event_id="queue-1", session="host-session",
            text="Return the local demo value", action=action),
    token=credential)
result = engine.execute("host-session", "queue-1", credential, lambda _: 42)
assert decision.final_decision == "ALLOW" and result["result"] == 42
engine.authority.revoke(grant_id)
```

The operator API is deliberately not exposed as a message/tool action. The caller may not supply
its own principal, source trust, session boundary, grants or approval classification.

## Before production integration

Use Galaxy as an additional veto upstream of JoyCtl. An ALLOW does not authorize execution:
the owning deterministic policy and runtime must still validate their own current ExecutionGrant.
Map authenticated actors and revision proofs explicitly, fail closed on unavailable owning policy,
and retain independent approval and revocation checks immediately at the actual dispatch boundary.

execute serializes local invocation with SQLite revocation. It is not a distributed grant executor.
A revocation committed before invocation is seen; a concurrent revocation waits for the writer
transaction. Callbacks must be bounded, nonreentrant local test operations. Remote effects need
runtime-controlled atomic grant consumption, durable dispatch IDs, reconciliation after crash and
cancellation. Do not infer those guarantees from a successful local example.

Next qualification should run an isolated read-only IntentStack client plus a real JoyCtl verifier,
then JoyEvidence authenticated audit delivery with idempotent outbox replay. Only after independent
review and crash/race testing should an approved runtime adapter be considered. No production change
or deployment is part of this milestone.
