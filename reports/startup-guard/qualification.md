# Guarded startup qualification

Date: 2026-11-05, Asia/Singapore.
Implementation commit: 59cf0bc.
Branch: work/startup-guard-20261105.
Checkout: /home/sam/galaxy-intentstack-startup-20261105.

## Result

The isolated GuardedControlPlane now starts CLOSED and requires verified composition and audit
bootstrap before native queueing, worker claims or verification recovery. Runtime health failures
latch FAILED. Readiness flags, file repair and entering drain cannot silently reopen that host.

Healthy drain permits native renewal of existing leases and retains worker custody facts without
manufacturing completion. A fresh activated owner recovers verification through existing JoyCtl.
Close waits for admitted guarded calls; a timeout leaves resources open for explicit retry.

## Evidence

Final installed-package qualification:
- **169 passed, 0 failed, 0 skipped, no warnings**, in 177.50 seconds.
- Previous 141 regression cases plus 28 new startup cases.
- Ruff checks and formatting passed for all 31 Python files.
- Eight real hard-process-exit recovery cases passed.
- Installed startup, controller and revocation module hashes match source.
- Fresh noneditable environment on Linux / Python 3.13.7; pip check found no broken requirements.
- Benchmarks and detector development/heldout/challenge outputs were regenerated.
  Detector rules and evaluation-corpus limitations are unchanged.

Independent existing joy-evidence console verification:
- Normal native integration: verified, 8 records.
- Dependency revocation: verified, 19 records.
- Guarded startup native execution: verified, 4 records.

The startup demonstration records READY with zero active calls, actual native sandbox success,
four authenticated audit acknowledgments and zero pending audit records. Its semantic acceptance
is false, its job state is failed under the unmet independent-review contract, physical attestation
is NOT_ESTABLISHED, and production_qualified is false. Native command success is not mission
semantic success.

The new hard-exit test constructs the actual guarded owner in a fresh spawned interpreter and
terminates with os._exit(98) before activation. On restart, claims remain denied until a new
successful bootstrap; the existing job is leased through native Unix placement. The previous
seven recovery tests also pass. See crash-recovery.json for cases and measured durations.

Security cases include closed constructor/readiness flag bypass, missing/altered composition,
source marker and audit corruption, ledger/key identity, user mismatch, unregistered/stopped
drains, pending revocation recovery, native revocation outage, immutable failure latch, restart,
healthy drain renewal, retained custody facts, recovered receipts, and bounded shutdown waiting.

Raw evidence is saved beside this report: tests.txt, tests.xml, lint.txt, format.txt,
clean-install.txt, package-reinstall.txt, interfaces.json, startup-demo.json,
integration-demo.json, revocation-demo.json and three independent audit-verification outputs.
Only the final completed run is represented here.

## Scope and remaining work

Qualified only for the stated isolated local-development SQLite composition. Production mode
is rejected. Direct unwrapped controllers do not gain these gates. Local host code, filesystem,
producer and key custody remain trusted; checks do not authenticate the whole filesystem.

The wrapper adds a veto and delegates actual authority, lease authentication, scheduling,
custody and verification to JoyCtl. It reuses existing dependency recovery and authenticated
audit. It creates no replacement grant authority, ledger or scheduler.

Health checks are entry-point checks. They do not create distributed atomic commit or cancel
an already-running command. Ordinary retained-event ingestion remains native-owned and its
transport must be quiesced by the owner before teardown. Per-admission full ledger verification
has not been qualified for production load.

Production startup wiring, OIDC, physical attestation, protected remote dependency/audit state,
distributed races and in-flight cancellation, operational scaling and independent review remain
open. No production qualification or deployment is established.

Earlier checkouts and user rerun evidence were preserved. No sudo, production service changes,
restarts, push or deployment was performed. Private test tokens, ledger keys and enrollment
markers are excluded from delivered outputs.

## Reproduce on joy

```sh
cd /home/sam/galaxy-intentstack-startup-20261105
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/startup-guard
```

Fresh setup uses python3 scripts/setup_phase2.py --venv .venv-phase2.
Design and lifecycle details: docs/startup-guard.md.
