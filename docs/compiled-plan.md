# Compiled-plan queue milestone

This follow-up removes Galaxy's deprecated raw-instruction queue path while preserving the
isolated, read-only scope. Work is on branch work/compiled-plan-20261105 in
/home/sam/galaxy-intentstack-compiled-plan-20261105. The prior checkout and the user's Phase 2
rerun reports remain untouched.

## Changes

Plan now pins prompt_id, expected_prompt_hash, admitted_plan_id and admitted_decision_id.
They are optional in parsing so old records remain readable, but every new dispatch requires
all four. Old plans cannot silently fall back to raw instructions.

The controller loads the prompt through the existing JoyCtl CompiledPromptStore configured with
require_tenant=True against the same canonical runtime database. This is significant:
JoyCtl's default development SQLite reader does not filter by organisation even when passed one.
The new cross-tenant regression initially failed, then passed with the enforcing configuration.
No upstream store code, database ownership or production configuration was changed.

Before queueing, the adapter checks:
- expected content hash and current stored text integrity;
- tenant and mission ownership;
- admitted plan, decision and step linkage;
- passed prompt validation;
- read_only_analysis profile and hosted target;
- all existing native grant, identity, device, resource and belief-precondition checks.

The owning queue receives prompt_id and expected_prompt_hash; it receives no instruction field.
Its current native authorization consumption, snapshot checks, aggregate-input pinning,
idempotency and recovery remain authoritative. A compiled prompt is not a grant.

## Real semantic admission

The canonical admitted step is also an aggregate step. JoyCtl requires a registered semantic
contract before it can be queued. The fixture uses the existing, already-built JoyLang kernel
to admit a real contract, and registers its literal test obligation with the native snapshot
verifier. Missing contracts remain denied by the owning queue; no control was removed.

The isolated contract also requires independent review. Tests never fabricate that evidence:
a successful read-only sandbox command still cannot establish review, physical attestation,
or general semantic completion. The native controller keeps that completion boundary.
The prompt compiler uses its existing deterministic fixture backend; no model API or key is used.
Security enforcement and the JoyLang admission/verification interfaces are real implementations.

## Compatibility and limits

Old Plan JSON can be parsed. New dispatch fails closed without the pins. Existing operation
bindings are not silently rewritten or automatically migrated: inspect historical jobs through
the owning controller, and obtain a properly bound compiled plan for new work. Never recycle
a consumed authorization or edit canonical records.

Production mode remains rejected. OIDC qualification, physical attestation, remote audit custody,
post-queue dependency revocation and independent review remain open. The local SQLite prompt
reader fix does not claim that every upstream client or production deployment was audited.

## Reproduce on joy

```sh
cd /home/sam/galaxy-intentstack-compiled-plan-20261105
python3 scripts/setup_phase2.py --venv .venv-phase2
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/compiled-plan
```

Linux, bwrap, JoyMux, Node and an existing built JoyLang kernel are required. Missing admission
infrastructure is BLOCKED, with no fake contract or automatic build of the upstream repository.
Only temporary test-owned HTTP/Unix services are started. No sudo, production writes, deployment
or push is part of this milestone. Test keys remain private in ignored work directories.
