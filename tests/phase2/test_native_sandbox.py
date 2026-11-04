"""Exercise actual JoyCtl custody and Linux read-only sandbox; never substitute a passed receipt."""

import base64
import hashlib
import json
from datetime import UTC, datetime

from .conftest import remember, retrieve, submit


def complete_with_retained_claims(f):
    lease = f.agent.claim()
    assert lease is not None

    def upload_payload(body):
        raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return {
            "evidence_type": "hosted_producer_claim",
            "artifact": {
                "encoding": "base64",
                "data": base64.b64encode(raw).decode(),
                "size_bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                **{k: lease[k] for k in ("mission_id", "execution_id", "workspace_ref")},
            },
        }

    chunk = upload_payload(
        {
            "schema": "joymesh.public-output/v1",
            "ordinal": 1,
            "stream": "stdout",
            "message": "Isolated worker reports a read-only observation",
        }
    )
    manifest = upload_payload(
        {
            "schema": "joymesh.output-artifact-manifest/v1",
            "scope": "public_redacted_output_excluding_private_records",
            "complete": True,
            "observed_records": 1,
            "uploaded_records": 1,
            "omitted_records": 0,
            "independent_verification": False,
            "records": [
                {
                    "ordinal": 1,
                    "sha256": chunk["artifact"]["sha256"],
                    "size_bytes": chunk["artifact"]["size_bytes"],
                }
            ],
        }
    )
    packets = [
        ("started", {}),
        ("evidence_produced", chunk),
        (
            "output",
            {"stream": "stdout", "message": "Isolated worker reports a read-only observation"},
        ),
        ("evidence_produced", manifest),
        ("completed", {"exit_code": 0}),
    ]
    outcome = None
    for sequence, (kind, payload) in enumerate(packets, 1):
        outcome = f.agent.event(
            lease["lease_id"],
            lease["lease_token"],
            {
                "protocol_version": "1",
                "event_id": f"isolated-event-{sequence}",
                "job_id": lease["job_id"],
                "execution_id": lease["execution_id"],
                "sequence": sequence,
                "timestamp": datetime.now(UTC).isoformat(),
                "type": kind,
                "payload": payload,
            },
        )
    row = f.plane.snapshot_verifications.get(f.plan.organisation_id, lease["job_id"])
    assert row["state"] == "receipted", row["error"]
    receipt = json.loads(row["receipt_json"])
    assert receipt["passed"] is True, row["receipt_json"]
    candidate = receipt["candidate"]
    raw = f.plane.hosted_artifact_custody.store.get({"artifact_id": candidate["content_reference"]})
    body = json.loads(raw)
    assert body["passed"] and not body["semantic_acceptance"]
    assert body["physical_attestation"] == "NOT_ESTABLISHED"
    assert all(
        r["sandbox"] == "linux-bwrap-readonly-no-network-v1" and r["exit_code"] == 0
        for r in body["receipts"]
    )
    # Successful process verification must not silently become semantic mission acceptance.
    assert not outcome["completion"]["verified"]
    return lease, body


def test_real_retrieval_authorization_custody_and_native_sandbox(
    integrated, retrieval_service, isolated_joymux
):
    f = integrated
    remember(retrieval_service, "The meeting is on Monday.")
    retrieve(f, retrieval_service)
    queued = submit(f)
    assert queued["controller_accepted"]
    lease, body = complete_with_retained_claims(f)
    assert lease["job_id"] == queued["job_id"]
    assert body["grant_id"] == f.native.execution_grant_id
    observed = f.integration.observe(
        operation_id="operation-1", human_token=f.human_token, device_token=f.device_token
    )
    assert observed["sandbox_passed"] and not observed["semantic_acceptance"]
    assert observed["audit"]["pending"] == 0
    import os
    from pathlib import Path

    report = os.environ.get("GALAXY_PHASE2_DEMO_REPORT")
    if report:
        Path(report).write_text(
            json.dumps(
                {
                    "source": "real localhost IntentStack DataAgent",
                    "dispatch": queued,
                    "observation": observed,
                    "native_receipt": body,
                    "audit_verification": f.ledger.verify(),
                    "audit_ledger_path": str(f.ledger.path),
                    "audit_key_path": str(f.ledger.key_path),
                    "joymux_transport": "isolated real Unix socket",
                    "production_integration_qualified": False,
                },
                indent=2,
                sort_keys=True,
            )
        )


def test_kill_after_sandbox_execution_before_authenticated_audit(integrated, isolated_joymux):

    from .test_process_recovery import killed, reopen

    f = integrated
    queued = submit(f)
    complete_with_retained_claims(f)
    killed(f, "execution-observed", 95)
    _, plane, delivery = reopen(f)
    first = f.integration.observe(
        operation_id="operation-1", human_token=f.human_token, device_token=f.device_token
    )
    again = f.integration.observe(
        operation_id="operation-1", human_token=f.human_token, device_token=f.device_token
    )
    assert first == again and first["audit"]["pending"] == 0
    assert submit(f)["job_id"] == queued["job_id"]
    with plane.database.connect() as c:
        assert (
            c.execute(
                "SELECT count(*) FROM execution_events WHERE event_type='completed'"
            ).fetchone()[0]
            == 1
        )
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 1
    with f.integration.engine.store.connection() as c:
        assert c.execute("SELECT count(*) FROM integration_observations").fetchone()[0] == 1
    assert delivery.ledger.verify()["records"] == delivery.status()["sink_acknowledged"]


def test_native_revocation_prevents_worker_lease(integrated, isolated_joymux):
    f = integrated
    outcome = submit(f)
    assert outcome["controller_accepted"]
    f.plane.snapshot_grant_authority.revoke(
        f.plan.organisation_id, f.native.execution_grant_id, "revoked before lease"
    )
    assert f.agent.claim() is None
    assert f.plane.get_job(f.principal, outcome["job_id"])["attempt_count"] == 0
