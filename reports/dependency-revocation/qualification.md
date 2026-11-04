# Dependency revocation qualification

Date: 2026-11-05, Asia/Singapore.
Implementation commit: 95d79b5.
Branch: work/dependency-revocation-20261105.
Checkout: /home/sam/galaxy-intentstack-revocation-20261105.

The previous compiled-plan checkout and the user's rerun evidence were preserved.
No sudo, production changes, service restarts, push or deployment was performed.

## Implementation

Added an additional dependency veto at the existing JoyCtl native grant-validation boundary,
plus durable forwarding into the existing native revocation API. The same wrapper is composed
into the isolated controller and its snapshot-verification registry. Issuance, grant authenticity,
scope, expiry, consumption, scheduling, execution and semantic acceptance remain upstream-owned.

Operator-declared required beliefs bind atomically to the native grant and dispatch intention.
A committed retraction, dispute, source-trust withdrawal, upstream memory correction or typed
negative claim revision stales dependent support and creates one durable revocation obligation.
Direct claim corrections now invalidate active graph support; positive verification never
silently revives a revoked dependency or grant.

The veto closes the forwarding-delay window: the real native admission/per-command boundary
rejects affected grants even while the original native record remains active and delivery is
pending. Forwarding subsequently calls JoyCtl's original revoke method and confirms the owning
store raises RevokedError before recording an acknowledgment.

The new local tables are dependency bindings, indexed links and forwarding obligations, not
a replacement grant system. Existing append-only audit and JoyEvidence delivery are reused.

Files: src/galaxy_intentstack/revocation.py and updates to audit.py, beliefs.py and controller.py;
tests/phase2/test_dependency_revocation.py and the existing fixture/recovery harness;
scripts/qualify_phase2.py. Details: docs/dependency-revocation.md.

## Evidence

Clean installed-package qualification:
- **141 passed, 0 failed, 0 skipped, no warnings**, in 176.24 seconds.
- The previous 113 regression cases pass, plus 28 new revocation cases.
- Ruff checks passed; all 29 Python files passed formatting.
- Seven actual hard-process-exit recovery cases passed (the previous five plus two new cases).
- The installed Galaxy revocation, belief, controller and storage modules match the source.
- Existing native grants, real HTTP retrieval, compiled prompts, JoyLang admission, Unix placement,
  custody, Linux sandbox verification and HMAC audit tests remain exercised.

Independent upstream joy-evidence console verification:
- Normal native integration demo: verified, **8 records**.
- Dependency revocation demo: verified, **19 records**.

The real retrieval-revision demo measured:
- a native job accepted with an operator-declared derived belief;
- an actual IntentStack Monday-to-Tuesday memory revision;
- stale derived support and one pending revocation obligation;
- **zero worker attempts** before forwarding;
- native revocation independently confirmed through the original store;
- one native acknowledgment, zero pending obligations, zero forwarding errors.

Raw evidence: tests.txt, tests.xml, lint.txt, format.txt, clean-install.txt,
package-reinstall.txt, interfaces.json, integration-demo.json, revocation-demo.json,
independent-audit-verification.txt, independent-revocation-audit-verification.txt,
and crash-recovery.json in this directory. Old baseline reports are historical; this directory
contains the final authoritative run.

## Security

Verified cases include:
- retraction, contradiction, source distrust and upstream revision;
- disputed/refuted typed claims and transitive derived support;
- real native lease rejection while revocation forwarding is pending or unavailable;
- actual native-store revocation after delivery;
- duplicate invalidation/delivery suppression and transaction rollback;
- unknown or altered forwarding targets rejected before reaching JoyCtl;
- unconfirmed revocation and forged local acknowledgment not treated as native confirmation;
- missing, recreated or corrupt dependency storage, missing enrollment and deleted links;
- legacy dependency records held for explicit review rather than silently reauthorized;
- attempted replacement of the registry composition or a different producer database rejected;
- valid current dependencies permitting actual native Unix placement and sandbox verification.

A retained private enrollment marker anchors the existing audit producer identity outside SQLite.
Read-only authorization checks never recreate a missing database. A fresh empty producer database
cannot silently restore old queued authority. This anchor is local trust configuration, not
cryptographic authentication of the whole filesystem or physical attestation.

The forwarding target is bound to the registered controller, organisation, native grant, operation
and causal invalidation event. No external message can create or clear that authority.
The producer chain is checked for tested corruption, but remains an unkeyed local chain; existing
JoyEvidence HMAC is the authenticated audit sink. Local host/storage/key owners are trusted.

A dispute can conservatively consume authority. Fresh review and a fresh native grant are needed;
memory correction does not automatically restore permission. This improves execution safety at
the cost of possible availability holds.

## Reliability

New hard-exit probes use fresh spawned interpreters and os._exit:
1. After committed graph invalidation, before forwarding.
2. After committed native revocation, before local acknowledgment.

On restart, the composition is installed before worker claims. The native lease remains denied,
pending obligations survive, and retry records one acknowledgment without new execution or grants.
The original five crash probes also continue to pass.

The two-command test invokes the actual first Linux read-only command, commits support
invalidation, and verifies that the next native command never reaches the spawn boundary.
It does not mock the native command result or fabricate a successful receipt.

There is no distributed atomic commit and no retroactive cancellation of an already-running
command. The tested checks occur at the owning admission, per-command/before-spawn and completion
boundaries. Evidence arriving after the last check can overlap in-flight work; this milestone
does not claim general exactly-once effects or physical cancellation.

Native-revocation acknowledgment and authenticated audit acknowledgment are distinct. Forwarding
failure preserves debt; audit delivery can be retried separately. Neither is remote attestation.

## Detector quality

Detector rules and fixtures were not changed. The qualification runner reproduces the existing
development, held-out and diagnostic challenge measurements and saves their outputs here.
The earlier limitations still apply: author-written, template-heavy held-out cases are not a
population accuracy estimate, and the feedback-tuned challenge is not an untouched holdout.
Classification and inference confidence remain independent of execution authority.

## Production qualification

| Level | Status |
|---|---|
| Local dependency-revocation implementation | Complete for the stated slice |
| Isolated composed-controller integration | Qualified under the tested conditions |
| Production integration | **BLOCKED / not qualified** |
| Production deployment | **Not authorized** |

The veto must be installed in the actual owning controller before enabling worker claims or
verification drain on every restart. Direct unwrapped controllers do not gain this protection.
Production bootstrap enforcement was not changed or qualified.

Production OIDC, physical attestation, protected remote dependency/audit state, distributed
in-flight cancellation, availability behavior and independent security review remain open.
No independent human review or remote witness was performed. Native sandbox success still does
not manufacture the contract's independent-review evidence or physical-attestation proof.

## Remaining work

1. Enforce the tested composition in an approved production-shaped startup/ingress rehearsal.
   Fail startup if the dependency store/anchor or wrapper registration is unavailable.
2. Qualify production identity, physical custody and remote dependency/audit authentication.
3. Test additional distributed races and explicit in-flight cancellation through the owners.
4. Obtain independent review and a broader blinded detector corpus before broad deployment.

Reproduce on host joy:
```sh
cd /home/sam/galaxy-intentstack-revocation-20261105
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/dependency-revocation
```

Fresh setup:
```sh
python3 scripts/setup_phase2.py --venv .venv-phase2
```

The runner validates both independent audit-verification responses and the zero-attempt/native-
revoked demonstration. Private test credentials, ledger keys and enrollment markers remain in
ignored work directories on joy and are excluded from deliverables.
