"""Actual os._exit in fresh spawned processes, using existing authority and ledger state."""

import multiprocessing
import os
from dataclasses import asdict

from joyctl.hosted import HostedConfig, HostedControlPlane
from joyevidence import Ledger

from galaxy_intentstack import Action, Engine, Message
from galaxy_intentstack.controller import Integration, JoyCtlController, Plan
from galaxy_intentstack.delivery import AuditDelivery

from .conftest import submit


def crash_worker(phase, data):
    if phase == "startup-before-activation":
        from galaxy_intentstack.startup import GuardedControlPlane

        GuardedControlPlane.sqlite(data["controller_path"], config=HostedConfig(**data["config"]))
        os._exit(98)
    engine = Engine(data["galaxy_path"])
    plane = HostedControlPlane.sqlite(
        data["controller_path"], config=HostedConfig(**data["config"])
    )
    plan = Plan.model_validate(data["plan"])
    delivery = AuditDelivery(
        engine.store,
        Ledger(data["sink_path"], data["key_path"]),
        user_id=plan.user_id,
        actor_id="galaxy-test",
    )
    integration = Integration(engine, JoyCtlController(plane, plan), delivery)
    if phase == "preparation":
        integration.submit(
            **data["request"],
            action=Action.model_validate(data["action"]),
            after_prepare=lambda: os._exit(91),
        )
    elif phase == "controller":
        integration.submit(
            **data["request"],
            action=Action.model_validate(data["action"]),
            after_dispatch=lambda: os._exit(92),
        )
    elif phase == "ledger":
        delivery.flush(after_append=lambda: os._exit(93))
    elif phase == "local-write":
        with engine.store.connection() as c:
            engine.store.event(c, "uncommitted_probe", {"probe": "rollback"})
            os._exit(94)
    elif phase == "dependency-invalidation":
        engine.beliefs.retract(data["revocation_evidence_id"])
        os._exit(96)
    elif phase == "native-dependency-revoke":
        integration.revocations.flush(after_native_revoke=lambda: os._exit(97))
    elif phase == "execution-observed":
        integration.observe(
            operation_id="operation-1",
            human_token=data["request"]["human_token"],
            device_token=data["request"]["device_token"],
            after_persist=lambda: os._exit(95),
        )


def killed(f, phase, expected):
    data = {
        "galaxy_path": f.engine.store.path,
        "controller_path": str(f.plane.database.path),
        "sink_path": str(f.ledger.path),
        "key_path": str(f.ledger.key_path),
        "config": asdict(f.config),
        "plan": f.plan.model_dump(),
        "action": f.action.model_dump(),
        "request": {
            "operation_id": "operation-1",
            "session": "integration-session",
            "human_token": f.human_token,
            "device_token": f.device_token,
        },
    }
    if hasattr(f, "revocation_probe_evidence"):
        data["revocation_evidence_id"] = f.revocation_probe_evidence
    child = multiprocessing.get_context("spawn").Process(target=crash_worker, args=(phase, data))
    child.start()
    child.join(20)
    if child.is_alive():
        child.kill()
        child.join()
        raise AssertionError("Crash probe hung")
    assert child.exitcode == expected


def reopen(f):
    engine = Engine(f.engine.store.path)
    plane = HostedControlPlane.sqlite(f.plane.database.path, config=f.config)
    delivery = AuditDelivery(
        engine.store,
        Ledger(f.ledger.path, f.ledger.key_path),
        user_id=f.plan.user_id,
        actor_id="galaxy-test",
    )
    f.integration = Integration(engine, JoyCtlController(plane, f.plan), delivery)
    return engine, plane, delivery


def test_process_kill_after_preparation_requires_current_authority(integrated):
    f = integrated
    killed(f, "preparation", 91)
    f.plane.snapshot_grant_authority.revoke(
        f.plan.organisation_id, f.native.execution_grant_id, "revoked after process kill"
    )
    _, plane, _ = reopen(f)
    assert submit(f)["decision"] == "DENY"
    with plane.database.connect() as c:
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 0


def test_process_kill_after_controller_commit_creates_only_one_job(integrated):
    f = integrated
    killed(f, "controller", 92)
    _, plane, delivery = reopen(f)
    a, b = submit(f), submit(f)
    assert a["controller_accepted"] and a["job_id"] == b["job_id"]
    with plane.database.connect() as c:
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 1
    assert delivery.require_current()["pending"] == 0


def test_process_kill_after_ledger_commit_does_not_duplicate_delivery(integrated):
    f = integrated
    f.engine.process(Message(event_id="one", session="s", text="Persisted evidence"))
    killed(f, "ledger", 93)
    _, _, delivery = reopen(f)
    result = delivery.require_current()
    assert result["pending"] == 0
    assert delivery.ledger.verify()["records"] == result["local_persisted"]


def test_process_kill_during_local_write_rolls_back_evidence_and_outbox(integrated):
    f = integrated
    killed(f, "local-write", 94)
    engine, _, delivery = reopen(f)
    with engine.store.connection() as c:
        assert not c.execute("SELECT 1 FROM events WHERE kind='uncommitted_probe'").fetchone()
        assert not c.execute("SELECT 1 FROM audit_outbox").fetchone()
    assert delivery.ledger.verify()["records"] == 0
