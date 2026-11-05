# Guarded startup and ingress

This milestone adds GuardedControlPlane, a local-development subclass of the existing JoyCtl
HostedControlPlane. Construct this class from the outset, compose the existing Integration,
then call plane.activate(integration) before enabling workers or verification recovery.

It starts CLOSED. Changing the native readiness flag cannot open it. Activation verifies the
same dependency authority is installed on both native owner boundaries, its original delegate
and controller identity, the enrolled producer store/anchor, audit principal, and the original
authenticated JoyEvidence ledger and key. It recovers durable native revocations and requires
current audit delivery before becoming READY. A pre-existing unregistered verification drain
prevents activation.

Queueing, native worker claims and native verification recovery check health on entry.
The existing readiness evaluator sees the same gate. Health failure latches FAILED; repairing
files or entering drain does not reopen the host. Use a fresh reviewed host and activate again.
Startup readiness is never persisted. Historical accepted-operation responses may still be
returned by reconciliation; they do not queue or execute a second job.

The subclass adds a veto, not a new grant authority, scheduler, ledger or execution engine.
JoyCtl still owns identity, grants, placement, lease authentication, custody, verification,
and semantic completion. JoyMux placement uses a private test daemon over Unix sockets only.

## Healthy draining and recovery

begin_drain stops new queueing, claims and verification. Existing leases can renew while the
composition remains healthy; native token, principal and expiry checks still apply. Workers
can submit already-running custody facts. When startup verification is closed, the native
event handler retains those facts and returns an explicitly non-authoritative pending result.
It creates no successful receipt. A fresh activated host can recover verification through the
existing JoyCtl recovery API.

close waits for admitted guarded calls with a bounded timeout before closing native resources.
A timeout leaves resources open for explicit retry. An already-running command is not
retroactively cancelled. Ordinary retained-event ingestion remains native-owned; an external
transport must still be quiesced by its owner before final resource teardown.

Use start_verification_drain after successful activation to attach the actual upstream drain.
An unexpected, stopped or failed drain closes readiness. Recovery remains delegated to JoyCtl.

## Qualification and limits

The tests cover closed construction, readiness flag bypass, correct bootstrap, missing or altered
composition/storage/audit/key, enrollment mismatch, pending or unavailable native revocation
recovery, healthy drain renewal, retained facts and fresh recovery, shutdown waiting and restart.
A fresh spawned process terminates with os._exit(98) after guarded construction and before
activation. The next host remains CLOSED until a new successful bootstrap.

A real native demonstration exercises Unix placement, Linux sandbox/custody verification and
authenticated audit. Native command success does not satisfy the independent human-review
contract or establish physical attestation.

This is isolated local-development SQLite qualification. Production mode is rejected.
Direct unwrapped HostedControlPlane instances do not gain these gates. The local host, code,
filesystem and key custody remain trusted. Checks are entry-point checks and do not create a
distributed atomic transaction or cancel an already-running command. Full ledger verification
on each admission is conservative and has not been qualified for production scale.

Production startup wiring, OIDC, physical attestation, protected remote state, distributed races
and cancellation, operational load and independent review remain open. No production service,
configuration or database was changed, and nothing was pushed or deployed.

## Reproduce on joy

```sh
cd /home/sam/galaxy-intentstack-startup-20261105
python3 scripts/setup_phase2.py --venv .venv-phase2
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/startup-guard
```

The runner uses installed noneditable packages and independently invokes the existing
joy-evidence console verifier for each demonstration. See reports/startup-guard/qualification.md.
Private keys, test tokens and enrollment markers remain outside delivered outputs.
