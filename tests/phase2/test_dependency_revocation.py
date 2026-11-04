"""Real native lease/command gates plus durable dependency revocation forwarding."""

import json
import os
from pathlib import Path

import pytest
from joyctl.hosted import AgentSession
from joyctl.runtime.hosted_verification import HostedVerificationError
from joyctl.schema_contracts import RevokedError

from galaxy_intentstack import Engine, Message
from galaxy_intentstack.controller import Integration
from galaxy_intentstack.delivery import AuditDelivery

from .conftest import remember, retrieve, submit
from .test_native_sandbox import complete_with_retained_claims


def supported_plan(f, *, derived=False):
    result = f.engine.process(
        Message(event_id="basis", session="integration-session", text="The meeting is on Monday."),
        source="meeting-owner",
    )
    belief = next(
        b["id"]
        for b in f.engine.beliefs.snapshot("integration-session")
        if b["subject"] == "meeting.day"
    )
    if derived:
        belief = f.engine.beliefs.derive("integration-session", "Prepare Monday briefing", [belief])
    f.plan = f.plan.model_copy(update={"required_belief_ids": (belief,)})
    f.controller.plan = f.plan
    f.action = f.action.model_copy(update={"belief_ids": (belief,)})
    return result, belief


def native_active(f):
    # Deliberately inspect the existing owning authority, beneath the additional veto.
    f.integration.dependency_authority.delegate.validate(
        f.plan.organisation_id, f.native, worker_authorization_id=f.plan.authorization_id
    )


def assert_no_lease(f, job_id):
    assert f.agent.claim() is None
    assert f.plane.get_job(f.principal, job_id)["attempt_count"] == 0


@pytest.mark.parametrize("change", ["retract", "contradict", "trust", "correction"])
def test_committed_dependency_change_blocks_native_lease_before_forwarding(integrated, change):
    f = integrated
    result, _ = supported_plan(f, derived=True)
    queued = submit(f)
    assert queued["controller_accepted"]
    if change == "retract":
        f.engine.beliefs.retract(result.evidence_references[0])
    elif change == "trust":
        f.engine.beliefs.source_trust("meeting-owner", trusted=False)
    elif change == "correction":
        f.engine.beliefs.source_trust("meeting-owner", authority=1, trusted=True)
        f.engine.process(
            Message(
                event_id="correction",
                session="integration-session",
                text="Correction: the meeting is on Tuesday.",
            ),
            source="meeting-owner",
        )
    else:
        f.engine.process(
            Message(
                event_id="contradiction",
                session="integration-session",
                text="The meeting is on Tuesday.",
            ),
            source="another-source",
        )
    native_active(f)
    assert f.integration.revocations.status()["pending"] == 1
    assert_no_lease(f, queued["job_id"])
    outcome = f.integration.revocations.flush()
    assert outcome["native_acknowledged"] == 1 and outcome["pending"] == 0
    with pytest.raises(RevokedError):
        f.integration.dependency_authority.delegate.store(f.plan.organisation_id).lookup_grant(
            f.native.execution_grant_id
        )
    f.delivery.require_current()
    assert f.ledger.verify()["records"] == f.delivery.status()["sink_acknowledged"]


def test_real_retrieval_revision_revokes_dependent_queued_authority(integrated, retrieval_service):
    f = integrated
    memory = remember(retrieval_service, "The meeting is on Monday.")
    retrieve(f, retrieval_service)
    parent = f.engine.beliefs.snapshot("integration-session")[0]["id"]
    child = f.engine.beliefs.derive("integration-session", "Monday preparation", [parent])
    f.plan = f.plan.model_copy(update={"required_belief_ids": (child,)})
    f.controller.plan = f.plan
    f.action = f.action.model_copy(update={"belief_ids": (child,)})
    queued = submit(f)
    assert queued["controller_accepted"]
    response = retrieval_service.client.post(
        f"/v1/memories/{memory['id']}/corrections",
        json={
            "text": "The meeting is on Tuesday.",
            "source_ref": "isolated:updated",
            "reason": "New source evidence",
            "expected_revision": 1,
        },
    )
    assert response.status_code == 200
    retrieve(f, retrieval_service, request_id="second")
    assert_no_lease(f, queued["job_id"])
    pending_before_forwarding = f.integration.revocations.status()["pending"]
    flushed = f.integration.revocations.flush()
    assert flushed["pending"] == 0 and flushed["native_acknowledged"] == 1
    with pytest.raises(RevokedError):
        f.integration.dependency_authority.delegate.store(f.plan.organisation_id).lookup_grant(
            f.native.execution_grant_id
        )
    f.delivery.require_current()
    report = os.environ.get("GALAXY_REVOCATION_DEMO_REPORT")
    if report:
        Path(report).write_text(
            json.dumps(
                {
                    "controller_accepted_job": queued["job_id"],
                    "worker_attempts": f.plane.get_job(f.principal, queued["job_id"])[
                        "attempt_count"
                    ],
                    "revocation": flushed,
                    "pending_before_forwarding": pending_before_forwarding,
                    "native_revoked": True,
                    "graph": f.engine.beliefs.snapshot("integration-session"),
                    "audit_verification": f.ledger.verify(),
                    "audit_ledger_path": str(f.ledger.path),
                    "audit_key_path": str(f.ledger.key_path),
                    "scope": "composed isolated owner, real retrieval revision and native grant revocation",
                    "production_qualified": False,
                },
                indent=2,
                sort_keys=True,
            )
        )


def test_revocation_outage_keeps_debt_and_native_lease_veto(integrated, monkeypatch):
    f = integrated
    result, _ = supported_plan(f)
    queued = submit(f)
    f.engine.beliefs.retract(result.evidence_references[0])
    actual = f.integration.dependency_authority.delegate.revoke

    def offline(*args, **kwargs):
        raise OSError("test native authority unavailable")

    monkeypatch.setattr(f.integration.dependency_authority.delegate, "revoke", offline)
    status = f.integration.revocations.flush()
    assert status["pending"] == 1 and status["native_acknowledged"] == 0
    native_active(f)
    assert_no_lease(f, queued["job_id"])
    monkeypatch.setattr(f.integration.dependency_authority.delegate, "revoke", actual)
    assert f.integration.revocations.flush()["pending"] == 0


def test_repeated_invalidation_and_delivery_are_idempotent(integrated):
    f = integrated
    result, _ = supported_plan(f, derived=True)
    assert submit(f)["controller_accepted"]
    f.engine.beliefs.retract(result.evidence_references[0])
    f.engine.beliefs.source_trust("meeting-owner", trusted=False)
    assert f.integration.revocations.status()["requested"] == 1
    first = f.integration.revocations.flush()
    with f.engine.store.connection() as c:
        before = c.execute(
            "SELECT count(*) FROM events WHERE kind='native_dependency_revocation_acknowledged'"
        ).fetchone()[0]
    assert f.integration.revocations.flush()["native_acknowledged"] == first["native_acknowledged"]
    with f.engine.store.connection() as c:
        assert (
            c.execute(
                "SELECT count(*) FROM events WHERE kind='native_dependency_revocation_acknowledged'"
            ).fetchone()[0]
            == before
            == 1
        )


def test_unrelated_belief_change_does_not_revoke_registered_grant(integrated):
    f = integrated
    supported_plan(f)
    assert submit(f)["controller_accepted"]
    unrelated = f.engine.process(
        Message(event_id="other", session="different-session", text="Unrelated report"),
        source="another-owner",
    )
    f.engine.beliefs.retract(unrelated.evidence_references[0])
    assert f.integration.revocations.status()["requested"] == 0
    f.plane.snapshot_grant_authority.validate(
        f.plan.organisation_id, f.native, worker_authorization_id=f.plan.authorization_id
    )


def test_invalidated_transaction_rollback_has_no_revocation_debt(integrated):
    f = integrated
    _, belief = supported_plan(f)
    assert submit(f)["controller_accepted"]
    with pytest.raises(RuntimeError), f.engine.store.connection() as c:
        f.engine.beliefs.invalidate(c, belief, "rolled back test")
        raise RuntimeError("abort before commit")
    assert f.integration.revocations.status()["requested"] == 0
    f.plane.snapshot_grant_authority.validate(f.plan.organisation_id, f.native)


def test_unconfirmed_native_revocation_is_never_acknowledged(integrated, monkeypatch):
    f = integrated
    result, _ = supported_plan(f)
    queued = submit(f)
    f.engine.beliefs.retract(result.evidence_references[0])
    monkeypatch.setattr(
        f.integration.dependency_authority.delegate, "revoke", lambda *args, **kwargs: None
    )
    status = f.integration.revocations.flush()
    assert status["pending"] == 1 and status["native_acknowledged"] == 0
    native_active(f)
    assert_no_lease(f, queued["job_id"])


@pytest.mark.parametrize("corruption", ["missing", "enrollment", "links", "audit"])
def test_dependency_store_failure_denies_owning_native_lease(integrated, corruption):
    f = integrated
    supported_plan(f)
    queued = submit(f)
    assert queued["controller_accepted"]
    if corruption == "missing":
        Path(f.engine.store.path).rename(f.engine.store.path + ".held")
    else:
        with f.engine.store.connection() as c:
            if corruption == "enrollment":
                c.execute("DELETE FROM execution_dependencies")
            elif corruption == "links":
                c.execute("DELETE FROM execution_dependency_links")
            else:
                c.execute("DROP TRIGGER events_no_update")
                c.execute("UPDATE events SET payload='{}' WHERE id=1")
    assert_no_lease(f, queued["job_id"])


def test_recreated_dependency_database_cannot_silently_reenroll(integrated):
    f = integrated
    supported_plan(f)
    queued = submit(f)
    Path(f.engine.store.path).rename(f.engine.store.path + ".held")
    recreated = Engine(f.engine.store.path)
    # Install a fresh audit producer just as a mistaken fresh setup might.
    AuditDelivery(recreated.store, f.ledger, user_id=f.plan.user_id, actor_id="galaxy-test")
    with pytest.raises(HostedVerificationError, match="enrollment"):
        Integration(recreated, f.controller, f.delivery)
    assert_no_lease(f, queued["job_id"])


def test_revocation_does_not_erase_belief_or_grant_history(integrated):
    f = integrated
    result, _ = supported_plan(f)
    assert submit(f)["controller_accepted"]
    f.engine.beliefs.retract(result.evidence_references[0])
    f.integration.revocations.flush()
    with f.engine.store.connection() as c:
        assert c.execute("SELECT text FROM evidence").fetchone()[0] == "The meeting is on Monday."
        assert (
            c.execute("SELECT count(*) FROM events WHERE kind='belief_revision'").fetchone()[0] > 0
        )
    store = f.integration.dependency_authority.delegate.store(f.plan.organisation_id)
    assert store.revision_history(f.native.execution_grant_id)


def test_current_dependency_allows_actual_native_sandbox(integrated, isolated_joymux):
    f = integrated
    supported_plan(f)
    assert submit(f)["controller_accepted"]
    complete_with_retained_claims(f)


@pytest.mark.parametrize(
    "integrated",
    [{"commands": ("/usr/bin/python3 verify.py", "/usr/bin/python3 verify_two.py")}],
    indirect=True,
)
def test_invalidation_between_real_native_commands_blocks_next_spawn(
    integrated, isolated_joymux, monkeypatch
):
    import joyctl.runtime.hosted_verification as module

    f = integrated
    result, _ = supported_plan(f)
    assert submit(f)["controller_accepted"]
    actual = module.verify_in_sandbox
    calls = []

    def verify_then_invalidate(*args, **kwargs):
        calls.append(args[1])
        receipts = actual(*args, **kwargs)
        f.engine.beliefs.retract(result.evidence_references[0])
        return receipts

    monkeypatch.setattr(module, "verify_in_sandbox", verify_then_invalidate)
    _, outcome, row = complete_with_retained_claims(f, expect_receipt=False)
    assert len(calls) == 1 and calls[0] == ("/usr/bin/python3 verify.py",)
    assert row["receipt_json"] is None
    assert not outcome["completion"]["verified"]
    assert f.integration.revocations.status()["pending"] == 1


@pytest.mark.parametrize(
    "phase,exitcode", [("dependency-invalidation", 96), ("native-dependency-revoke", 97)]
)
def test_hard_exit_recovers_dependency_revocation_without_reexecution(integrated, phase, exitcode):
    from .test_process_recovery import killed, reopen

    f = integrated
    result, _ = supported_plan(f, derived=True)
    f.revocation_probe_evidence = result.evidence_references[0]
    queued = submit(f)
    assert queued["controller_accepted"]
    if phase == "native-dependency-revoke":
        f.engine.beliefs.retract(result.evidence_references[0])
    killed(f, phase, exitcode)
    _, plane, delivery = reopen(f)
    session = AgentSession(plane, f.device_token)
    assert session.claim() is None
    assert plane.get_job(f.principal, queued["job_id"])["attempt_count"] == 0
    assert f.integration.revocations.status()["pending"] == 1
    flushed = f.integration.revocations.flush()
    assert flushed["pending"] == 0 and flushed["native_acknowledged"] == 1
    assert f.integration.revocations.flush()["native_acknowledged"] == 1
    with pytest.raises(RevokedError):
        f.integration.dependency_authority.delegate.store(f.plan.organisation_id).lookup_grant(
            f.native.execution_grant_id
        )
    delivery.require_current()
    assert delivery.ledger.verify()["records"] == delivery.status()["sink_acknowledged"]


def test_legacy_unbound_dependency_operation_is_held_before_native_lease(integrated):
    from galaxy_intentstack.audit import canonical, digest

    f = integrated
    supported_plan(f)
    # Reproduce the actual preceding version's native queue and persisted operation shape.
    job = f.plane.queue_execution(
        f.principal,
        mission_id=f.plan.mission_id,
        step_id=f.plan.step_id,
        authorization_id=f.plan.authorization_id,
        prompt_id=f.plan.prompt_id,
        expected_prompt_hash=f.plan.expected_prompt_hash,
        idempotency_key="pre-guard-operation",
    )
    with f.engine.store.connection() as c:
        c.execute(
            "INSERT INTO integration_operations VALUES(?,?,?,'accepted',?,?)",
            (
                "legacy",
                digest(f.plan.model_dump()),
                "integration-session",
                job["id"],
                canonical(f.plan.model_dump()),
            ),
        )
    native_active(f)
    assert_no_lease(f, job["id"])


def test_missing_anchor_blocks_restart_and_existing_native_checks(integrated):
    f = integrated
    supported_plan(f)
    queued = submit(f)
    f.integration.dependency_authority.marker.unlink()
    with pytest.raises(HostedVerificationError, match="enrollment"):
        Integration(f.engine, f.controller, f.delivery)
    assert_no_lease(f, queued["job_id"])


def test_owner_cannot_silently_bind_another_dependency_database(integrated, tmp_path):
    f = integrated
    other = Engine(tmp_path / "another.db")
    AuditDelivery(other.store, f.ledger, user_id=f.plan.user_id, actor_id="galaxy-test")
    with pytest.raises(HostedVerificationError, match="different dependency"):
        Integration(other, f.controller, f.delivery)


def test_replacing_native_registry_guard_is_detected(integrated):
    f = integrated
    f.plane.snapshot_verifications.grant_authority = f.integration.dependency_authority.delegate
    with pytest.raises(HostedVerificationError, match="replaced"):
        Integration(f.engine, f.controller, f.delivery)


def test_poisoned_revocation_target_is_not_forwarded(integrated, monkeypatch):
    f = integrated
    result, _ = supported_plan(f)
    assert submit(f)["controller_accepted"]
    f.engine.beliefs.retract(result.evidence_references[0])
    with f.engine.store.connection() as c:
        c.execute("UPDATE dependency_revocations SET grant_id='unrelated-grant'")
    calls = []
    monkeypatch.setattr(
        f.integration.dependency_authority.delegate,
        "revoke",
        lambda *args, **kwargs: calls.append(args),
    )
    status = f.integration.revocations.flush()
    assert status["pending"] == 1 and status["native_acknowledged"] == 0
    assert calls == []


def test_forged_local_revocation_acknowledgment_is_rejected(integrated):
    f = integrated
    result, _ = supported_plan(f)
    assert submit(f)["controller_accepted"]
    f.engine.beliefs.retract(result.evidence_references[0])
    with f.engine.store.connection() as c:
        c.execute("UPDATE dependency_revocations SET acknowledged=1")
    with pytest.raises(ValueError, match="audited native confirmation"):
        f.integration.revocations.status()


@pytest.mark.parametrize("state", ["DISPUTED", "REFUTED"])
def test_typed_claim_revision_invalidates_queued_support(integrated, state):
    from galaxy_intentstack import State

    f = integrated
    result, _ = supported_plan(f, derived=True)
    queued = submit(f)
    assert queued["controller_accepted"]
    changed = result.extracted_claims[0].model_copy(update={"state": State(state)})
    with f.engine.store.connection() as c:
        f.engine.beliefs.update_claim(c, changed)
    assert f.integration.revocations.status()["pending"] == 1
    assert_no_lease(f, queued["job_id"])
    assert f.integration.revocations.flush()["native_acknowledged"] == 1
