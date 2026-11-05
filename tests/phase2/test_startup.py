"""Actual owner entry points must stay closed until guarded bootstrap is healthy."""

import json
import os
import threading
import time
from pathlib import Path

import pytest
from joyctl.deploy.readiness import evaluate_readiness
from joyctl.hosted import AgentSession, HostedConfig, HostedControlPlane
from joyctl.runtime.hosted_verification_drain import HostedVerificationDrain
from joyevidence import Ledger

from galaxy_intentstack import Engine, Message
from galaxy_intentstack.controller import Integration, JoyCtlController
from galaxy_intentstack.delivery import AuditDelivery
from galaxy_intentstack.startup import GuardedControlPlane, StartupDenied

from .conftest import submit
from .test_dependency_revocation import supported_plan
from .test_native_sandbox import complete_with_retained_claims


@pytest.fixture
def host(integrated, request):
    request.addfinalizer(integrated.plane.close)
    return integrated


def seed(f):
    f.engine.process(
        Message(event_id="health-probe", session="health", text="Private test evidence")
    )
    f.delivery.require_current()


def reopen(f):
    plane = GuardedControlPlane.sqlite(f.plane.database.path, config=f.config)
    engine = Engine(f.engine.store.path)
    delivery = AuditDelivery(
        engine.store,
        Ledger(f.ledger.path, f.ledger.key_path),
        user_id=f.plan.user_id,
        actor_id="galaxy-test",
    )
    integration = Integration(engine, JoyCtlController(plane, f.plan), delivery)
    return plane, integration


@pytest.mark.parametrize("integrated", [{"guarded_startup": True}], indirect=True)
class TestGuardedStartup:
    def test_constructor_does_not_open_queue_claim_or_recovery(self, host, monkeypatch):
        f = host
        calls = []
        actual = HostedControlPlane.claim_job

        def record(*args, **kwargs):
            calls.append("native-claim")
            return actual(*args, **kwargs)

        monkeypatch.setattr(HostedControlPlane, "claim_job", record)
        assert f.plane.startup_status()["state"] == "CLOSED"
        assert not evaluate_readiness(f.plane).ready
        with pytest.raises(StartupDenied):
            f.agent.claim()
        with pytest.raises(StartupDenied):
            f.plane.resume_pending_snapshot_verifications()
        with pytest.raises(StartupDenied):
            f.plane.start_verification_drain()
        assert submit(f)["decision"] == "DENY"
        assert calls == []
        with f.plane.database.connect() as c:
            assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 0

    def test_setting_readiness_flag_cannot_bypass_bootstrap(self, host):
        f = host
        f.plane._accepting_work = True
        assert not f.plane._accepting_work
        with pytest.raises(StartupDenied):
            f.agent.claim()

    def test_healthy_bootstrap_opens_actual_native_queue(self, host):
        f = host
        assert f.plane.activate(f.integration)["ready"]
        assert evaluate_readiness(f.plane).ready
        result = submit(f)
        assert result["controller_accepted"], result
        assert f.plane.get_job(f.principal, result["job_id"])["compatibility_mode"] is False
        assert f.plane.activate(f.integration)["ready"]  # same composition is idempotent

    @pytest.mark.parametrize("failure", ["registry", "marker", "source", "ledger", "key"])
    def test_startup_failure_latches_closed(self, host, failure):
        f = host
        seed(f)
        if failure == "registry":
            f.plane.snapshot_verifications.grant_authority = (
                f.integration.dependency_authority.delegate
            )
        elif failure == "marker":
            f.integration.dependency_authority.marker.unlink()
        elif failure == "source":
            with f.engine.store.connection() as c:
                c.execute("DROP TRIGGER events_no_update")
                c.execute("UPDATE events SET payload='{}' WHERE id=1")
        elif failure == "ledger":
            with f.ledger.connection() as c:
                c.execute("UPDATE records SET envelope='{}' WHERE sequence=1")
        else:
            f.ledger.key_path.unlink()
        with pytest.raises(StartupDenied):
            f.plane.activate(f.integration)
        assert f.plane.startup_status()["state"] == "FAILED"
        assert not evaluate_readiness(f.plane).ready
        with pytest.raises(StartupDenied):
            f.agent.claim()

    @pytest.mark.parametrize("failure", ["registry", "marker", "ledger", "key"])
    def test_runtime_failure_closes_native_admission(self, host, failure):
        f = host
        seed(f)
        f.plane.activate(f.integration)
        if failure == "registry":
            f.plane.snapshot_verifications.grant_authority = (
                f.integration.dependency_authority.delegate
            )
        elif failure == "marker":
            f.integration.dependency_authority.marker.unlink()
        elif failure == "ledger":
            with f.ledger.connection() as c:
                c.execute("UPDATE records SET record_mac=? WHERE sequence=1", ("0" * 64,))
        else:
            f.ledger.key_path.unlink()
        # Existing upstream readiness sees the composed gate, without a separate caller probe.
        assert not evaluate_readiness(f.plane).ready
        assert f.plane.startup_status()["state"] == "FAILED"
        with pytest.raises(StartupDenied):
            f.agent.claim()
        with pytest.raises(StartupDenied):
            f.plane.resume_pending_snapshot_verifications()

    def test_recovery_does_not_automatically_reopen_failed_host(self, host):
        f = host
        marker = f.integration.dependency_authority.marker
        original = marker.read_text()
        marker.unlink()
        with pytest.raises(StartupDenied):
            f.plane.activate(f.integration)
        marker.write_text(original)
        with pytest.raises(StartupDenied):
            f.plane.activate(f.integration)
        assert f.plane.startup_status()["state"] == "FAILED"

    def test_wrong_audit_principal_cannot_bootstrap(self, host):
        f = host
        with f.engine.store.connection() as c:
            c.execute("UPDATE delivery_meta SET user_id='foreign-principal'")
        with pytest.raises(StartupDenied):
            f.plane.activate(f.integration)

    def test_missing_composition_fails_cleanly(self, host):
        with pytest.raises(StartupDenied):
            host.plane.activate(None)
        assert host.plane.startup_status()["state"] == "FAILED"
        assert host.plane.startup_status()["active_calls"] == 0

    def test_graceful_drain_stops_new_work_without_reopening(self, host):
        f = host
        f.plane.activate(f.integration)
        f.plane.begin_drain()
        assert not evaluate_readiness(f.plane).ready
        with pytest.raises(StartupDenied):
            f.agent.claim()
        with pytest.raises(StartupDenied):
            f.plane.resume_pending_snapshot_verifications()
        with pytest.raises(StartupDenied):
            f.plane.activate(f.integration)

    def test_existing_native_background_drain_is_guarded(self, host):
        f = host
        drain = HostedVerificationDrain(f.plane, interval=0.02, batch_size=1)
        drain.start()
        try:
            deadline = time.monotonic() + 5
            while drain.last_error is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert drain.last_error == "StartupDenied"
            with pytest.raises(StartupDenied):
                f.plane.activate(f.integration)  # unregistered early thread is not adopted
        finally:
            assert drain.stop()

    def test_registered_native_drain_requires_and_monitors_ready_state(self, host):
        f = host
        f.plane.activate(f.integration)
        drain = f.plane.start_verification_drain(interval=0.02, batch_size=1)
        deadline = time.monotonic() + 5
        while drain.last_result is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert drain.last_result is not None and drain.last_error is None
        assert evaluate_readiness(f.plane).ready
        assert drain.stop()
        assert not evaluate_readiness(f.plane).ready
        assert f.plane.startup_status()["state"] == "FAILED"

    def test_pending_revocation_must_be_recovered_before_reopen(self, host):
        f = host
        result, _ = supported_plan(f)
        f.plane.activate(f.integration)
        queued = submit(f)
        assert queued["controller_accepted"]
        f.engine.beliefs.retract(result.evidence_references[0])
        plane, integration = reopen(f)
        try:
            session = AgentSession(plane, f.device_token)
            with pytest.raises(StartupDenied):
                session.claim()
            assert integration.revocations.status()["pending"] == 1
            assert plane.activate(integration)["ready"]
            assert integration.revocations.status()["pending"] == 0
            assert session.claim() is None
            assert plane.get_job(f.principal, queued["job_id"])["attempt_count"] == 0
        finally:
            plane.close()

    def test_unavailable_revocation_recovery_refuses_startup(self, host, monkeypatch):
        f = host
        result, _ = supported_plan(f)
        f.plane.activate(f.integration)
        assert submit(f)["controller_accepted"]
        f.engine.beliefs.retract(result.evidence_references[0])
        plane, integration = reopen(f)

        def offline(*args, **kwargs):
            raise OSError("native revocation service unavailable")

        monkeypatch.setattr(integration.dependency_authority.delegate, "revoke", offline)
        try:
            with pytest.raises(StartupDenied):
                plane.activate(integration)
            assert integration.revocations.status()["pending"] == 1
            assert plane.startup_status()["state"] == "FAILED"
        finally:
            plane.close()

    def test_real_native_execution_requires_healthy_bootstrap(self, host, isolated_joymux):
        f = host
        status = f.plane.activate(f.integration)
        assert submit(f)["controller_accepted"]
        _, receipt = complete_with_retained_claims(f)
        assert receipt["passed"] and not receipt["semantic_acceptance"]
        observed = f.integration.observe(
            operation_id="operation-1", human_token=f.human_token, device_token=f.device_token
        )
        report = os.environ.get("GALAXY_STARTUP_DEMO_REPORT")
        if report:
            Path(report).write_text(
                json.dumps(
                    {
                        "startup": status,
                        "observation": observed,
                        "native_passed": receipt["passed"],
                        "physical_attestation": receipt["physical_attestation"],
                        "audit_verification": f.ledger.verify(),
                        "audit_ledger_path": str(f.ledger.path),
                        "audit_key_path": str(f.ledger.key_path),
                        "production_qualified": False,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )

    def test_draining_retains_facts_then_fresh_host_recovers_verification(
        self, host, isolated_joymux
    ):
        f = host
        f.plane.activate(f.integration)
        queued = submit(f)
        lease = f.agent.claim()
        assert lease is not None
        f.plane.begin_drain()
        renewed = f.plane.renew_lease(
            f.agent.principal, lease_id=lease["lease_id"], lease_token=lease["lease_token"]
        )
        assert renewed["lease_id"] == lease["lease_id"]
        _, outcome, row = complete_with_retained_claims(f, expect_receipt=False, lease=lease)
        assert outcome["accepted"] and not outcome["completion"]["verified"]
        assert outcome["completion"]["reason"] == "galaxy_startup_not_ready"
        assert row["receipt_json"] is None
        with f.plane.database.connect() as c:
            assert c.execute("SELECT count(*) FROM execution_events").fetchone()[0] == 5
        plane, integration = reopen(f)
        try:
            assert plane.activate(integration)["ready"]
            recovered = plane.resume_pending_snapshot_verifications()
            assert recovered["outcomes"]
            receipt = plane.snapshot_verifications.get(f.plan.organisation_id, queued["job_id"])
            assert json.loads(receipt["receipt_json"])["passed"]
            historical = submit(f)
            assert historical["job_id"] == queued["job_id"]
            assert not historical["executed"]
            with pytest.raises(StartupDenied):
                f.agent.claim()
        finally:
            plane.close()

    def test_drain_does_not_clear_failed_health_latch(self, host):
        f = host
        f.plane.activate(f.integration)
        original = f.plane.snapshot_grant_authority
        f.plane.snapshot_grant_authority = original.delegate
        assert not f.plane.startup_status()["ready"]
        f.plane.snapshot_grant_authority = original
        f.plane.begin_drain()
        assert f.plane.startup_status()["state"] == "FAILED"
        with pytest.raises(StartupDenied):
            f.plane.renew_lease(f.agent.principal, lease_id="absent", lease_token="absent")

    def test_replacing_a_valid_audit_sink_latches_closed(self, host):
        f = host
        f.plane.activate(f.integration)
        f.delivery.ledger = Ledger(f.root / "other-ledger.jsonl", f.root / "other-key")
        assert not f.plane.startup_status()["ready"]
        assert f.plane.startup_status()["state"] == "FAILED"

    def test_shutdown_waits_for_admitted_work(self, host):
        f = host
        f.plane.activate(f.integration)
        entered, release = threading.Event(), threading.Event()

        def work():
            with f.plane._work():
                entered.set()
                assert release.wait(5)

        worker = threading.Thread(target=work)
        worker.start()
        assert entered.wait(2)
        try:
            with pytest.raises(StartupDenied, match="resources were left open"):
                f.plane.close(timeout=0)
            assert f.plane.startup_status()["active_calls"] == 1
            with f.plane.database.connect() as c:
                assert c.execute("SELECT 1").fetchone()[0] == 1
        finally:
            release.set()
            worker.join(5)
        f.plane.close()
        assert f.plane.startup_status()["state"] == "STOPPED"

    def test_process_exit_before_activation_stays_closed_on_restart(self, host, isolated_joymux):
        from .test_process_recovery import killed

        f = host
        f.plane.activate(f.integration)
        queued = submit(f)
        f.plane.begin_drain()
        killed(f, "startup-before-activation", 98)
        plane, integration = reopen(f)
        try:
            assert not plane.startup_status()["ready"]
            with pytest.raises(StartupDenied):
                plane.claim_job(f.agent.principal)
            assert plane.activate(integration)["ready"]
            lease = plane.claim_job(f.agent.principal)
            assert lease["job_id"] == queued["job_id"]
        finally:
            plane.close()

    def test_readiness_is_not_persisted(self, host):
        f = host
        f.plane.activate(f.integration)
        plane, integration = reopen(f)
        try:
            assert plane.startup_status()["state"] == "CLOSED"
            with pytest.raises(StartupDenied):
                plane.claim_job(f.agent.principal)
            assert plane.activate(integration)["ready"]
        finally:
            plane.close()


def test_production_mode_cannot_construct_this_isolated_host(tmp_path):
    from dataclasses import replace

    config = replace(HostedConfig(), mode="production")
    with pytest.raises(StartupDenied):
        GuardedControlPlane.sqlite(tmp_path / "not-created.db", config=config)
