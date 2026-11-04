# Architecture

This document describes the Phase 1 compatibility layer. For the implemented Phase 2 real
integration and current boundaries, see [Phase 2 architecture](phase2-architecture.md).

The package is an independent library with optional read-only adapters.

```text
Message -> bounded validation -> durable evidence -> REPORTED / INFERRED claim
        -> candidate interpretations -> uncertain pattern observations
        -> belief update / dependent invalidation -> independent authorization
        -> ALLOW / DENY / CLARIFY / ABSTAIN / ESCALATE -> audit + persisted decision
```

All pipeline writes commit in one SQLite BEGIN IMMEDIATE transaction. A conflicting replay
fails and rolls back; an identical (session,event_id) replay returns the original historical
decision. That result must be revalidated by execute before local invocation.

- models.py: strict immutable Pydantic boundaries, seven epistemic states.
- audit.py: WAL SQLite persistence, FULL synchronization, transactional audit,
  append-only triggers, SHA256 predecessor links and content commitments.
- beliefs.py: advisory graph with fresh-node dependencies (no public cycle insertion),
  contradiction handling, explicit verification, retraction and source trust updates.
- analysis.py: deterministic observable lexical patterns and ambiguous interpretations.
- authorization.py: operator-owned identity registry, credential digests, scoped expiring
  grants, independent approval, revocation and global policy kill switch.
- engine.py: atomic pipeline and revalidation before bounded local callback invocation.
- integrations.py: incoming message, memory revision/source_ref, classifier, action,
  local policy-check and bounded audit export adapters.
- api.py: JSON-lines demo CLI; no server or production endpoint.

Evidence text is preserved separately from audit/log content. The observed presence of a message
does not make its assertions OBSERVED or VERIFIED: normal assertions enter as REPORTED.
Citations and derivations enter as INFERRED and retain original roots. Exact repetition by the
same source reuses the root, and no count of sources or repetitions grants verification.
The verifier capability permits an explicit independent attestation; its factual quality remains
the verifier's responsibility. Confidence defaults to uncalibrated and does not grant anything.

Meeting-day recognition is the deliberately narrow semantic vertical slice. Within one session,
a correction by an enrolled trusted source at equal (same source) or greater source authority,
and later local ingestion time, may supersede the earlier slot. Otherwise both claims become
disputed. Local chronology is not proof of real-world truth or cross-store causal ordering.
All correction transitions append prior belief snapshots and stale descendants. The system does
not rewrite calendars. Session represents one meeting topic in this slice.

Graph creation requires active same-session parents. Retraction invalidates every claim carrying
the evidence and traverses descendants. Source trust withdrawal invalidates source-derived nodes.
Explicit derive links retain support roots and evidence. Unsupported or disputed dependencies
cannot satisfy an action's required beliefs. Required beliefs must also be explicitly VERIFIED.

SQLite persists all state; restart does not need a model or in-memory cache. Startup checks the
local audit chain. This is not authenticated projection reconstruction: an owner who rewrites the
entire database is outside this library's enforcement boundary. v0.1 adds a fail-closed binding
column for early local development grants; no production migration is offered.

Bounds: 12,000 message characters; 32 supplied references/parents; 256 accumulated provenance
references/roots in the message path; 10,000 claims per session through the pipeline;
10,000 nodes per invalidation traversal; 256 events per audit export; five-second writer timeout.
Operator graph methods and total database/session count remain operator-controlled and need
quotas before public service exposure. Source trust updates scan affected local nodes.
