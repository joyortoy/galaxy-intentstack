# Dependency revocation milestone

Branch: work/dependency-revocation-20261105
Checkout: /home/sam/galaxy-intentstack-revocation-20261105

This is an isolated local read-only integration. It adds a dependency veto to the existing
JoyCtl grant boundary and forwards revocation to JoyCtl's existing durable store. It does not
issue grants, run a replacement scheduler, change production configuration, or cancel an
already-running physical effect.

## Invariant and ownership

Once a supporting belief change is committed, a subsequent native validation on the composed
controller must reject the affected grant. Forwarding does not have to finish first.

An outbox alone cannot provide that property: a queued worker could claim the old native grant
before the revocation sender recovers. Integration therefore installs DependencyAuthority around
the existing native authority and binds the **same object** into the controller's existing
snapshot-verification registry. All native policy checks still run first. The additional veto
reads the registered dependencies; it never creates positive authority.

The real native worker-admissibility, authorization_state, before-spawn checks and completion
fence reuse this boundary. Tests call the actual AgentSession.claim directly, not a Galaxy-only
worker wrapper. A valid dependency still permits actual Unix placement and bwrap verification.

## Durable state

- execution_dependencies: native controller/grant/operation/session and operator-plan commitment.
- execution_dependency_links: required belief references, checked against the committed binding.
- dependency_revocations: one monotonic forwarding obligation per controller/organisation/grant.
- Existing append-only events and JoyEvidence audit_outbox: causal registration, invalidation,
  forwarding failure and confirmed native revocation.

These are additional veto/forwarding records, not a new grant authority. Native grant identity,
hash, scope, expiry, consumption and revocation remain in JoyCtl.

Binding and dispatch preparation commit together before queue acceptance. Invalidation writes the
belief revision and revocation obligation in the same SQLite transaction. Downstream invalidation
also reaches grants bound to derived beliefs. Direct typed claim revisions to disputed/refuted or
inactive validity propagate through active graph support; positive verification never revives nodes.

RevocationDelivery.flush uses the original owning revoke API and confirms RevokedError from the
owning store before acknowledging. It verifies the causal enrollment/event/target before sending.
A dropped response, unavailable authority, unknown target or unconfirmed revoke leaves debt pending.
A local acknowledgment flag without its audited native-confirmation event is rejected.

## Restart and storage loss

The existing authenticated audit producer identity is retained in a private
<database>.dependencies.json enrollment marker. A missing/replaced producer database or marker
cannot silently become an empty trusted store after restart. Authorization checks open SQLite in
read-only mode and never recreate it. The marker is local trust configuration, not a signing key,
physical attestation or protection from a fully compromised filesystem owner.

A restarted controller must install Integration before permitting worker claims, draining native
verifications or opening worker ingress. Existing dependency-bound operations without enrollment
are held for explicit review; they are not silently reauthorized. A controller already bound to
another producer store, or whose registry wrapper was replaced, is rejected.

## Usage in the isolated composition

```python
integration = Integration(engine, controller, delivery)  # before native worker claims
# Operator Plan.required_belief_ids and Action.belief_ids must agree.
result = integration.submit(
    operation_id=operation_id, session=session, action=action,
    human_token=human_token, device_token=device_token,
)
engine.beliefs.retract(evidence_id)
# Native validation now vetoes the affected grant, even before forwarding.
revocation_status = integration.revocations.flush()
audit_status = delivery.require_current()
```

Never expose operator Plan/enrollment configuration as instructions in retrieved text.
Forwarding and audit delivery have separate acknowledgments. A confirmed native revocation does
not imply that its audit has already reached the sink. Neither acknowledgment is remote physical
attestation.

## Tested boundaries

Tests use real IntentStack retrieval/revision, JoyCtl native grants and lease checks, actual
JoyMux Unix placement, real Linux sandbox commands, and existing JoyEvidence HMAC verification.
Failure injection changes timing or service availability, not core security decisions.

Coverage includes retraction, contradiction, trust withdrawal, upstream revision, typed claim
revision, transitive support, pending/outage forwarding, duplicates, rollback, storage corruption,
re-enrollment attempts, legacy holds, wrong composition, and forged target/ack projections.

Two fresh spawned processes terminate with os._exit:
- after committed belief invalidation, before forwarding;
- after native revocation, before local acknowledgment.

Recovery retains pending debt, denies native leases and retries without new execution or grants.
A two-command native sandbox probe actually executes the first command, invalidates its support,
and demonstrates that the next command is blocked before spawn. It does not claim cancellation
of the first command after it has started.

## Qualification limits

The local native controller and producer filesystem are trusted. The producer hash-chain check
detects tested corruption but is not a substitute for the existing HMAC audit sink or a remote
witness. A dispute can conservatively consume authority; fresh review and a fresh grant are needed.
No text, confidence score or restored memory automatically revives a revoked grant.

There is no distributed atomic commit between producer and controller and no retroactive rollback
of an already-started command. The native checks are at the existing admission, per-command and
completion boundaries; later evidence changes can overlap in-flight work. Direct unwrapped
controllers do not gain this veto. Production requires enforced bootstrap wiring, real production
identity/attestation, protected remote state and race/cancellation qualification. Production mode
remains rejected.

## Reproduce on joy

```sh
cd /home/sam/galaxy-intentstack-revocation-20261105
python3 scripts/setup_phase2.py --venv .venv-phase2
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/dependency-revocation
```

No sudo, push, deployment or production service restart is required. Private keys and enrollment
markers stay in ignored work directories. See reports/dependency-revocation/qualification.md
for final measured evidence and exact boundaries.
