"""Adapter to existing JoyCtl native lifecycle and hosted queue; no grant issuance."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from pydantic import Field

from .audit import canonical, digest
from .models import Action, Model


class IntegrationDenied(PermissionError):
    pass


class DispatchUncertain(RuntimeError):
    pass


class Plan(Model):
    organisation_id: str = Field(min_length=1, max_length=200)
    user_id: str = Field(min_length=1, max_length=200)
    device_id: str = Field(min_length=1, max_length=200)
    mission_id: str = Field(min_length=1, max_length=200)
    step_id: str = Field(min_length=1, max_length=200)
    authorization_id: str = Field(min_length=1, max_length=200)
    verification_id: str = Field(min_length=1, max_length=200)
    workspace_ref: str = Field(min_length=1, max_length=200)
    required_belief_ids: tuple[str, ...] = Field(default=(), max_length=32)
    require_physical_attestation: bool = True


class JoyCtlController:
    """Operator configures a registered read-only plan. Never build Plan from retrieved text."""

    INSTRUCTION = "Inspect the controller-registered read-only snapshot and retain evidence."

    def __init__(self, plane, plan: Plan):
        self.plane, self.plan = plane, plan

    def context(self, human_token, device_token):
        try:
            if self.plane.config.mode != "local-development":
                raise IntegrationDenied(
                    "This adapter is qualified only for isolated local development"
                )
            human = self.plane.verify_human_token(human_token)
            device = self.plane.verify_agent_token(device_token)
            p = self.plan
            if (human.user_id, human.organisation_id) != (p.user_id, p.organisation_id) or (
                device.device_id,
                device.organisation_id,
            ) != (p.device_id, p.organisation_id):
                raise IntegrationDenied("Authenticated user/device/organisation mismatch")
            if p.require_physical_attestation:
                raise IntegrationDenied(
                    "Physical attestation is unavailable; credential is not attestation"
                )
            return human
        except IntegrationDenied:
            raise
        except Exception as exc:
            raise IntegrationDenied("JoyCtl identity verification denied or unavailable") from exc

    def validate(self, human_token, device_token, action: Action, *, offered_grant=None):
        human = self.context(human_token, device_token)
        p = self.plan
        if (action.kind, action.resource, action.scope) != (
            "verify_snapshot",
            p.workspace_ref,
            "read",
        ):
            raise IntegrationDenied("Action does not match the registered read-only plan")
        if action.belief_ids != p.required_belief_ids:
            raise IntegrationDenied("Required belief conditions differ from the operator plan")
        try:
            row = self.plane._snapshot_authorization_row(p.organisation_id, p.verification_id)
            if row is None or row["revoked"]:
                raise IntegrationDenied("Registered plan absent or revoked")
            template = self.plane.snapshot_verifications.template(row)
            if any(
                template[k] != value
                for k, value in (
                    ("mission_id", p.mission_id),
                    ("step_id", p.step_id),
                    ("worker_authorization_id", p.authorization_id),
                    ("workspace_ref", p.workspace_ref),
                )
            ):
                raise IntegrationDenied("Mission, step, authorization or workspace mismatch")
            with self.plane.database.connect() as connection:
                project = connection.execute(
                    "SELECT p.device_id FROM hosted_projects p JOIN hosted_missions m "
                    "ON m.project_id=p.id WHERE m.id=? AND m.organisation_id=?",
                    (p.mission_id, p.organisation_id),
                ).fetchone()
            if not project or project["device_id"] != p.device_id:
                raise IntegrationDenied("Controller project is not pinned to the authorized device")
            from joyctl.policy import ExecutionGrant, NetworkPolicy
            from joyctl.runtime.hosted_verification import authorize_snapshot_grant

            native = dict(template["grant"])
            native["allowed_paths"] = tuple(native["allowed_paths"])
            native["allowed_tools"] = tuple(native["allowed_tools"])
            native["network_policy"] = NetworkPolicy(native["network_policy"])
            grant = offered_grant or ExecutionGrant(**native)
            if canonical(asdict(grant)) != canonical(template["grant"]):
                raise IntegrationDenied("Offered grant differs from controller plan")
            # Integrity hash alone is not authenticity: reload exact content from native store.
            self.plane.snapshot_grant_authority.validate(
                p.organisation_id, grant, worker_authorization_id=p.authorization_id
            )
            authorize_snapshot_grant(
                grant,
                root=Path(template["snapshot_root"]),
                commands=tuple(template["commands"]),
                mission_id=p.mission_id,
                verifier_identity=self.plane.snapshot_verifier_identity,
                intent_revision=template["current_intent_revision"],
                policy_revision=template["current_policy_revision"],
                timeout_seconds=template["timeout_seconds"],
            )
            return human, grant
        except IntegrationDenied:
            raise
        except Exception as exc:
            raise IntegrationDenied(
                "Native JoyCtl grant verification denied or unavailable"
            ) from exc

    def queue(self, human_token, device_token, action, key):
        human, _ = self.validate(human_token, device_token, action)
        p = self.plan
        # Owning controller atomically consumes worker authorization and checks native preflight.
        from joyctl.hosted import AuthorizationError, ConflictError, ValidationError

        try:
            return self.plane.queue_execution(
                human,
                mission_id=p.mission_id,
                step_id=p.step_id,
                authorization_id=p.authorization_id,
                instruction=self.INSTRUCTION,
                idempotency_key=key,
            )
        except (AuthorizationError, ConflictError, ValidationError) as exc:
            raise IntegrationDenied("Owning controller refused dispatch") from exc
        except Exception as exc:
            raise DispatchUncertain(
                "Controller acceptance is unknown; reconcile the same operation"
            ) from exc

    def reconcile(self, human_token, device_token, key):
        # Reporting a previously accepted job does not reauthorize it or invoke a worker.
        human = self.context(human_token, device_token)
        p = self.plan
        with self.plane.database.connect() as c:
            rows = c.execute(
                "SELECT id,constraints_json FROM execution_jobs WHERE "
                "organisation_id=? AND mission_id=?",
                (p.organisation_id, p.mission_id),
            ).fetchall()
        for row in rows:
            binding = json.loads(row["constraints_json"]).get("controller_request", {})
            if binding.get("key_sha256") == hashlib.sha256(key.encode()).hexdigest():
                return self.plane.get_job(human, row["id"])
        return None


class Integration:
    def __init__(self, engine, controller, delivery):
        self.engine, self.controller, self.delivery = engine, controller, delivery

    def submit(
        self,
        *,
        operation_id,
        session,
        action,
        human_token,
        device_token,
        recommendation="ALLOW",
        after_prepare=None,
        after_dispatch=None,
    ):
        if recommendation not in ("ALLOW", "DENY", "CLARIFY"):
            raise ValueError("Unsupported recommendation")
        binding = digest(
            [self.controller.plan.model_dump(), action.model_dump(), session, recommendation]
        )
        key = "galaxy:" + digest([operation_id, binding])
        try:
            self.controller.context(human_token, device_token)
            if recommendation != "ALLOW":
                raise IntegrationDenied("Galaxy recommendation does not permit dispatch")
            with self.engine.store.connection() as c:
                old = c.execute(
                    "SELECT * FROM integration_operations WHERE id=?", (operation_id,)
                ).fetchone()
                if old and old["binding"] != binding:
                    raise IntegrationDenied("Conflicting operation replay")
                for belief_id in action.belief_ids:
                    belief = c.execute(
                        "SELECT * FROM beliefs WHERE id=? AND session=?", (belief_id, session)
                    ).fetchone()
                    if not belief or belief["status"] != "active":
                        raise IntegrationDenied("Required belief is stale, disputed or absent")
                if not old:
                    c.execute(
                        "INSERT INTO integration_operations VALUES(?,?,?,'prepared',NULL,?)",
                        (
                            operation_id,
                            binding,
                            session,
                            canonical(self.controller.plan.model_dump()),
                        ),
                    )
                    self.engine.store.event(
                        c,
                        "dispatch_prepared",
                        {"operation_id": operation_id, "binding": binding, "key": key},
                    )
            if after_prepare:
                after_prepare()
            # Recover accepted controller jobs before treating expired/revoked authority as a new request.
            job = self.controller.reconcile(human_token, device_token, key)
            if job is None:
                self.controller.validate(human_token, device_token, action)
                self.delivery.require_current()
                # Do not hold a separate SQLite grant fence across worker execution.
                with self.engine.store.connection() as guard:
                    for belief_id in action.belief_ids:
                        current = guard.execute(
                            "SELECT status FROM beliefs WHERE id=? AND session=?",
                            (belief_id, session),
                        ).fetchone()
                        if not current or current[0] != "active":
                            raise IntegrationDenied(
                                "Required belief changed before controller acceptance"
                            )
                    job = self.controller.queue(human_token, device_token, action, key)
                if after_dispatch:
                    after_dispatch()
            with self.engine.store.connection() as c:
                row = c.execute(
                    "SELECT state FROM integration_operations WHERE id=?", (operation_id,)
                ).fetchone()
                if row[0] != "accepted":
                    c.execute(
                        "UPDATE integration_operations SET state='accepted',job_id=? WHERE id=?",
                        (job["id"], operation_id),
                    )
                    self.engine.store.event(
                        c,
                        "controller_accepted",
                        {"operation_id": operation_id, "job_id": job["id"], "binding": binding},
                    )
            # An outage after acceptance leaves a pending obligation, never repeats execution.
            try:
                audit = self.delivery.require_current()
            except Exception:  # noqa: BLE001 -- durable acceptance is distinct from audit delivery
                audit = self.delivery.status()
            return {
                "decision": "ALLOW",
                "controller_accepted": True,
                "executed": False,
                "job_id": job["id"],
                "job_state": job["state"],
                "audit": audit,
                "authority": "JoyCtl",
                "physical_attestation": "NOT_ESTABLISHED",
            }
        except DispatchUncertain:
            with self.engine.store.connection() as c:
                self.engine.store.event(c, "dispatch_uncertain", {"operation_id": operation_id})
            return {
                "decision": "ABSTAIN",
                "controller_accepted": None,
                "executed": False,
                "reason": "Controller acceptance is unknown; reconcile the same operation",
            }
        except IntegrationDenied as exc:
            with self.engine.store.connection() as c:
                self.engine.store.event(
                    c, "integration_denied", {"operation_id": operation_id, "reason": str(exc)}
                )
            return {
                "decision": "DENY",
                "controller_accepted": False,
                "executed": False,
                "reason": str(exc),
            }
        except Exception as exc:  # noqa: BLE001 -- fail closed across external verification adapters
            with self.engine.store.connection() as c:
                self.engine.store.event(
                    c,
                    "integration_unavailable",
                    {"operation_id": operation_id, "error_type": type(exc).__name__},
                )
            return {
                "decision": "DENY",
                "controller_accepted": False,
                "executed": False,
                "reason": "Required authorization or authenticated evidence unavailable",
            }

    def observe(self, *, operation_id, human_token, device_token, after_persist=None):
        """Retain a verified native sandbox receipt; never promote semantic/physical acceptance."""
        human = self.controller.context(human_token, device_token)
        with self.engine.store.connection() as c:
            op = c.execute(
                "SELECT * FROM integration_operations WHERE id=?", (operation_id,)
            ).fetchone()
            if (
                not op
                or not op["job_id"]
                or op["plan"] != canonical(self.controller.plan.model_dump())
            ):
                raise IntegrationDenied("No accepted operation for current plan")
        plane = self.controller.plane
        job = plane.get_job(human, op["job_id"])
        row = plane.snapshot_verifications.get(self.controller.plan.organisation_id, job["id"])
        if not row or not row["request_json"] or not row["receipt_json"]:
            raise IntegrationDenied("No retained native execution receipt")
        from joyctl.runtime.hosted_verification import SnapshotVerificationRequest
        from joyctl.runtime.hosted_verification_registry import _grant

        data = json.loads(row["request_json"])
        data["grant"] = _grant(data["grant"])
        data["claim_references"] = tuple(data["claim_references"])
        data["commands"] = tuple(data["commands"])
        request = SnapshotVerificationRequest(**data)
        receipt = plane.snapshot_verifications.cached_receipt(
            request, plane.hosted_artifact_custody.store
        )
        if receipt is None:
            raise IntegrationDenied("Native receipt validation unavailable")
        decision = receipt.boundary.decide(receipt.candidate)
        body = json.loads(receipt.boundary.verified_bytes(decision))
        payload = {
            "operation_id": operation_id,
            "job_id": job["id"],
            "execution_id": request.execution_id,
            "job_state": job["state"],
            "receipt_commitment": receipt.candidate.content_hash,
            "sandbox_passed": receipt.passed,
            "semantic_acceptance": body["semantic_acceptance"],
            "physical_attestation": body["physical_attestation"],
        }
        observation_id = digest(payload)
        with self.engine.store.connection() as c:
            prior = c.execute(
                "SELECT 1 FROM integration_observations WHERE id=?", (observation_id,)
            ).fetchone()
            if not prior:
                c.execute(
                    "INSERT INTO integration_observations VALUES(?,?,?)",
                    (observation_id, operation_id, canonical(payload)),
                )
                self.engine.store.event(c, "native_execution_observed", payload)
        if after_persist:
            after_persist()
        audit = self.delivery.require_current()
        return {**payload, "sandbox_execution_observed": True, "audit": audit}
