# Compiled-plan milestone qualification

Date: 2026-11-05 (Asia/Singapore).
Branch: work/compiled-plan-20261105.
Checkout: /home/sam/galaxy-intentstack-compiled-plan-20261105.
The original Phase 2 checkout and user-generated rerun reports were preserved.

## Implementation

Replaced Galaxy's deprecated instruction= queue path with the actual JoyCtl
prompt_id / expected_prompt_hash interface. Plan also pins the admitted plan and decision.
Prompts must match the tenant, mission, admitted step, plan and decision, and have passed
validation with the read_only_analysis profile and hosted target.

The adapter uses JoyCtl's existing CompiledPromptStore with require_tenant=True against the
same canonical runtime database. A regression test initially exposed that the development
SQLite store ignores organisation filters in its default configuration. The tenant-enforcing
configuration fixes Galaxy's boundary; no upstream production store was modified.

Canonical queue acceptance also requires a semantic contract for the admitted aggregate step.
The tests use the actual existing JoyLang kernel to admit it, register the literal test command
with JoyCtl's native snapshot verifier, and preserve the controller's aggregate-input pinning.
No fake admitted contract, raw-instruction fallback, new grant issuer or model API was added.

Old Plan records remain parseable. New dispatch without the compiled pins is denied.
Existing operation bindings are not silently migrated or rewritten.

## Evidence

- **113 tests passed, 0 failed, 0 skipped, no warnings** from the clean installed package.
- This includes the existing 93 regression cases and 20 new compiled-plan cases.
- The full installed run took 96.27 seconds on the actual development filesystem.
- Ruff checks passed; all 27 Python files passed formatting checks.
- A separate upstream joy-evidence console process verified 7 authenticated demo records.
- interfaces.json confirms the installed controller matches the working source and fingerprints
  the real prompt store, compiler, intake, native plan checks and existing JoyLang CLI.
- Existing native sandbox, process-kill recovery, authenticated delivery, revocation, replay,
  poisoning and belief-integrity tests continue to pass.

Raw evidence: tests.txt, tests.xml, clean-install.txt, independent-audit-verification.txt,
integration-demo.json, lint.txt, format.txt and interfaces.json in this directory.

New cases cover:
- canonical queue compatibility_mode=false and absence of instruction=;
- no deprecation warnings or silent fallback;
- missing prompt/hash/plan/decision pins;
- changed hash, missing prompt, wrong plan/decision/mission/step;
- failed validation, wrong profile or target;
- foreign-tenant prompts;
- stored prompt text tampering;
- changing a prompt pin while replaying an operation;
- owning-controller rejection when the registered semantic contract is absent.

## Security and reliability

Existing identity, physical-attestation rejection, exact native grant validation, device pinning,
belief-precondition rechecks, one-use authorization, idempotency and authenticated outbox remain
in place. A content hash proves neither authorization nor factual truth.

The sandbox receipt passed, but the actual controller job has state=failed because the fixture's
real semantic contract also requires independent review. No review evidence is supplied.
This deliberate unmet obligation is preserved: native process success does not grant semantic
completion or physical attestation. The audit outbox has zero pending records after recovery.

Existing crash probes still use real process exits and actual durable controller/ledger state.
No production services, configuration or databases were changed. No sudo, push or deployment.

## Qualification boundaries

- Local compiled-plan implementation: complete.
- Isolated read-only integration: qualified under the stated tests.
- Production OIDC, physical attestation, remote audit custody, post-queue dependency revocation
  and independent review: still unqualified.
- Production deployment: not authorized.

The deterministic fixture backend proposes prompt content; actual upstream compiler validation,
prompt storage, native authorization, JoyLang admission, custody and sandbox enforcement remain
real implementations. The built kernel is required; the runner does not silently build or replace it.
Detector code/fixtures were not changed in this milestone; broader semantic quality limitations
from Phase 2 still apply.

## Reproduce on joy

```sh
cd /home/sam/galaxy-intentstack-compiled-plan-20261105
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/compiled-plan
```

For a fresh environment, first run:
```sh
python3 scripts/setup_phase2.py --venv .venv-phase2
```

See docs/compiled-plan.md for the interface changes and remaining production boundaries.
