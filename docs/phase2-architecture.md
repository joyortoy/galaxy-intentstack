# Phase 2 isolated integration and trust boundaries

This implements an isolated **read-only snapshot verification** slice. It does not enable
consequential production tools. Core-only users retain the Phase 1 API and Python 3.11+ support;
JoyCtl integration requires Python 3.12+, Linux, bwrap, and an installed JoyMux binary.

## Ownership

IntentStack owns canonical memories, access filtering, revisions, and revision proofs.
JoyCtl owns native ExecutionGrant issuance/verification, worker authorization consumption,
job idempotency, device routing, custody and verification. JoyMux owns placement over Unix RPC.
JoyEvidence owns HMAC authentication, ordering, checkpoint integrity and duplicate ingestion.
Galaxy adds an advisory snapshot/graph and a forwarding outbox, not replacement authorities.

Phase 1 Authority and Engine.execute remain compatibility/test APIs. The Phase 2 path does not
use them to issue or authorize real JoyCtl jobs. Phase 2 installs upstream packages from accessible local repositories into ignored virtual
environments; no upstream source is vendored or committed.

## End-to-end flow

1. IntentStackRetrieval uses the actual DataAgent POST /v1/retrieve interface with
   include_evidence=true and require_recorded=true. Existing transport rules, identity filtering,
   five-result limit, exact-revision commitments and response-size bounds remain in force.
2. The complete response commits as a retrieval snapshot before advisory imports. Replay uses
   persisted bytes; all item imports and graph revisions are atomic. Claim metadata preserves
   actor, store, memory ID, source_ref, revision, creation/update times and upstream status.
   A recorded revision is still REPORTED, including an upstream confirmed memory.
3. An upstream newer revision supersedes the same memory's earlier local node and stales its
   descendants. Distinct contradictory records remain disputed. No text becomes system policy.
4. An operator configures a Plan from an existing controller-registered snapshot plan. Source text
   cannot select the plan, principal, device, workspace, commands, approval policy or grant.
5. JoyCtlController checks signed local-development human/device sessions, current enrollment,
   exact user/organisation/device/mission/step/workspace/action/role binding, operator-required
   belief conditions, a project pinned to the device, and the native grant's exact durable record.
   It invokes HostedSnapshotGrantAuthority.validate and authorize_snapshot_grant. Native hashes
   provide integrity; authenticity requires the trusted registry, not a self-supplied hash.
6. Galaxy persists a dispatch intention and requires verified JoyEvidence delivery before dispatch.
   Required beliefs are rechecked under the Galaxy writer lock while the owning controller accepts
   the queue request. The lock covers acceptance only, never worker command execution.
7. The real JoyCtl queue consumes authorization atomically and uses its existing idempotency key.
   A returned ALLOW means controller acceptance; executed=false remains explicit. A lost response
   yields ABSTAIN with unknown acceptance, followed by reconciliation using the same operation key.
8. Qualification starts a private, temporary JoyMux daemon using --data-dir ... serve --unix.
   It exercises the real Rust placement RPC without MCP or an in-process placement substitute.
   A test transport supplies worker claims; actual JoyCtl custody and Linux bwrap verification
   independently check the registered read-only snapshot and retain the execution receipt.
9. Integration.observe validates that retained receipt through the actual custody EvidenceBoundary
   and cached_receipt interface. It preserves semantic_acceptance=false and
   physical_attestation=NOT_ESTABLISHED; successful commands do not complete the mission.
10. Local event and JoyEvidence-format forwarding obligation commit together. The existing Ledger
    authenticates each envelope and retained checkpoint. Only an exact digest receipt plus ledger
    verification can acknowledge it. Local acknowledgment flags are checked against sink records.
    A separate joy-evidence process verifies the demonstration ledger.

## Modules

- retrieval.py: real upstream DataAgent adapter and deterministic snapshot import.
- controller.py: Plan, native grant/context gate, owning queue reconciliation and receipt observation.
- delivery.py: forwarding enrollment, outbox replay and acknowledgment verification.
- audit.py: additive SQLite snapshot/operation/outbox tables and private file permissions.
- models.py: additive typed memory provenance.
- analysis.py: observable contextual rules, still independent of authorization.
- scripts/setup_phase2.py: isolated installation from existing local checkouts.
- scripts/qualify_phase2.py: actual services, process-kill probes, demo and independent audit verification.

Existing Phase 1 message replay fingerprints remain compatible when new provenance is absent.
SQLite schema additions preserve existing tables. Database files are created/chmodded 0600;
new parent directories are 0700. Existing parent directory permissions are not broadened.

## Failure and recovery

| Boundary | Persisted owner state | Recovery |
|---|---|---|
| Retrieval captured; import interrupted | Galaxy response snapshot | Replay identical evidence atomically without network |
| Advisory update interrupted | SQLite transaction | Roll back graph/evidence/outbox together |
| Dispatch prepared; process dies | Galaxy immutable operation key | Revalidate current native authority before new acceptance |
| Controller accepts; response/local receipt lost | JoyCtl canonical job and consumed authorization | Reconcile same job; no second queue or new grant |
| Native verification completes; observation interrupted | JoyCtl custody receipt | Verify retained bytes; do not rerun commands |
| Observation commits; audit sink unavailable | Galaxy forwarding outbox | Replay after restart; report pending vs acknowledged |
| Ledger appends; producer acknowledgment lost | JoyEvidence stable source/event ID | already_recorded with matching digest; no duplicate |
| Revocation before queue/lease | Existing native lifecycle | Deny or no lease; no alternate execution path |
| Ledger/outbox tampering | HMAC/checkpoint or commitment mismatch | Fail closed; do not sign or dispatch |

These are the specifically tested boundaries, not a proof of every possible distributed race.

## Remaining limits

The adapter intentionally rejects production controller mode. Device credentials are not physical
attestation, and attestation-required plans fail closed. Audit sink acknowledgment is to a separate
local JoyEvidence Ledger, not a remote service; remote_acknowledged=false is explicit.

Queueing currently uses JoyCtl's deprecated instruction compatibility path, which compiles and
persists before acceptance. Migrating to the production prompt_id/admitted-plan path remains
required. No native grant fence is held across command execution.

Galaxy belief checks are additional vetoes at queue acceptance. Production must bind subsequent
dependency changes to the owning controller's revocation/dispatch boundary before allowing
consequential effects. The isolated read-only verifier does not turn reported memory into authority.

The producer database and HMAC key holders remain trusted. Local HMAC is not a remote witness,
hardware attestation, factual truth guarantee or defense against a fully compromised operator.
No arbitrary external-effect exactly-once claim is made.
