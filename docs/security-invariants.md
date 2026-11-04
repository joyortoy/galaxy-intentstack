# Security invariants

1. Inference is not verification. Only the trusted explicit verifier path can mark a claim VERIFIED.
2. Verification is not authorization. A matching independently configured grant is still mandatory.
3. Message, memory, classifier and tool content cannot enroll identities or change policy.
4. Grants bind the full action, actor, session, exact kind/resource/scope and validity period.
5. Missing identity, wrong scope/resource, expiry, revocation, disabled policy, stale beliefs,
   missing approval and principal mismatch fail closed.
6. When marked necessary by operator policy, approval requires a different authenticated identity
   with approve capability and a current approval. Disabling that identity blocks pending execution.
7. Consequential execution revalidates in the same SQLite writer transaction as local invocation;
   revocations committed first are observed. See integration.md for external-runtime limitations.
8. New graph nodes cannot cite stale, missing or cross-session parents.
9. Corrections and invalidations append audit events and retain original evidence.
10. Idempotency is keyed by host-assigned session and event identity and binds content and principal.
    Conflicting replay fails; successful pipeline writes and audit commit atomically.
11. Logs contain event ID and decision only. Audit contains commitments, IDs and structured policy
    metadata, not raw evidence text or bearer credentials. Common secret-shaped content is rejected
    before ingestion. This is a heuristic, not a complete DLP system; the trusted caller must
    remove secrets from content and identifiers.
12. Historical ALLOW output is never an execution capability.

Automated assertions: tests/adversarial/test_required_scenarios.py,
tests/unit/test_security_boundaries.py, tests/integration/test_adapters.py.
