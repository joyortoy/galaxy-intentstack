# Phase 2 discovery, before integration code

Baseline reproduced on host joy: 39 passed; 240 benchmark decisions; zero unauthorized ALLOWs
and unsupported VERIFIED promotions; precision .76923, recall .83333, benign FPR .25.
Raw baseline records: reports/phase2/baseline-tests.txt and baseline-benchmark.json.

Read-only sources: IntentStack release 20261010-4d5acdb-389af3e, JoyEvidence sibling,
JoyCtl 959d8b1 working checkout, JoyMux 3642ff8 working checkout. Working-tree hashes will be
recorded with qualification, because commit IDs alone do not identify uncommitted interfaces.

| Owner | Actual integration surface | Durable state / recovery |
|---|---|---|
| IntentStack | DataAgent.retrieve -> POST /v1/retrieve, limit <=5, require_recorded | Scope-filtered memories, immutable revisions, outbox + HMAC ledger |
| JoyCtl | policy.evaluate_policy/is_grant_valid; HostedSnapshotGrantAuthority.validate | Exact native grant content, current durable revision, revocation |
| JoyCtl | HostedControlPlane.queue_execution | Existing atomic authorization consumption and idempotency key replay |
| JoyCtl | snapshot registration/preflight, HostedSnapshotVerifier | Mission/action/role/source/commands bindings, custody, read-only sandbox receipts |
| JoyCtl | verify_human_token, verify_agent_token | Existing authenticated principal and enrolled device revocation |
| JoyMux | Unix computer-control / runtime boundaries | Physical execution custody remains outside Galaxy |
| JoyEvidence | Ledger.append/verify, joy.evidence.v1 envelopes | HMAC record chain and authenticated retained checkpoint; duplicate identity suppression |
| Galaxy | Persisted retrieval snapshot and advisory dependency graph | Never canonical memory; exact replay; revision-driven invalidation |
| Galaxy | Transactional forwarding outbox | Local event commitment -> existing JoyEvidence ledger -> verified acknowledgment |

Trust boundaries: retrieved text never configures policy, sessions, identity, commands or approval.
Galaxy's Phase 1 local authority remains backward-compatible for tests only; Phase 2 never uses it
to issue or authorize JoyCtl execution. The local unkeyed audit is a forwarding source, not the
authenticated evidence authority. No replacement memory engine, grant issuer or HMAC ledger.

Native grants have an integrity hash, not a signature. Authenticity comes from exact comparison
against JoyCtl's trusted durable store and existing principal verification. Recomputing the hash
does not enroll a forged grant. Registered read-only snapshot plans remain controller-owned.

A paired device credential is not physical attestation. Existing snapshot receipts explicitly say
physical_attestation=NOT_ESTABLISHED. Any path requiring such attestation must remain blocked;
this isolated slice cannot qualify real physical effects or live JoyMux dispatch without that
owning boundary. No test may relabel a credential as physical attestation.

Integration will use existing controller idempotency for durable dispatch, rather than inventing
a second execution-consumption engine. A crash after controller acceptance but before local receipt
must replay the same immutable request key and reconcile the same canonical job.
Remote JoyEvidence service ingestion is not present in the inspected package. This slice uses an
independent local Ledger sink with test enrollment keys, and must not claim remote acknowledgment.

Deployment constraints: development/tests only on host joy in private temporary paths. No production
configuration, databases, service restarts, MCP connections, pushes or deployment.
