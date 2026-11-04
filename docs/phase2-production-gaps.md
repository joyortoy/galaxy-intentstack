# Remaining production qualification gaps

The local read-only integration is qualified under its tested conditions. The following are
**BLOCKED / NOT QUALIFIED**, not hidden passes:

1. Production controller mode. The adapter currently refuses it. Replace the development HMAC
   login boundary with the existing production OIDC/audience authority in an approved isolated
   rehearsal. The compiled prompt_id/admitted-plan queue path is now qualified in the isolated
   follow-up (docs/compiled-plan.md); production OIDC remains unqualified. No production
   credentials were requested, copied or used.
2. Physical device/agent attestation. The real native receipt says NOT_ESTABLISHED. Maintain the
   fail-closed requirement; qualify through the owning JoyMux custody/attestation authority.
   A paired device token, successful Unix placement or successful bwrap command is insufficient.
3. Remote audit custody and independent witness. Only the existing local JoyEvidence ledger was
   integrated. No remotely acknowledged service exists in the inspected package. Define an
   authenticated transport and key-custody boundary, reuse its ledger/outbox semantics, and
   qualify loss, replay, corruption and acknowledgment before claiming remote delivery.
4. Consequential external effects. No transfers, calendar changes, privileged tools or production
   mission completion are enabled. Existing JoyCtl owns authorization consumption and worker
   dispatch. Prove post-queue belief invalidation/native revocation propagation, cancellation,
   callback-free effect reconciliation and remaining cross-service races before adding effects.
5. Broad manipulation classification. The held-out fixtures are small and template-heavy.
   The extra challenge initially failed badly and was used for feedback; the post-feedback result
   is not independent evidence. One selective-evidence paraphrase still misses. Obtain a larger
   independently annotated, blinded evaluation set with real multi-turn and multilingual cases.
6. Deployment and independent security review. No production configuration, service, database,
   release or GitHub push was changed. Perform an independent review of the new adapters and
   owning upstream contracts, then obtain explicit deployment authorization.

The project does not introduce another memory authority, grant issuer, authenticated ledger or
runtime. Its local Phase 1 compatibility APIs should not be exposed as production authority.
Test enrollment keys stay in private work directories and are excluded from Git/deliverables.
