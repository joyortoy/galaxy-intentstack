"""Additional dependency veto and durable forwarding to the owning JoyCtl revocation API."""

import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from .audit import canonical, digest


def controller_reference(plane):
    return digest(str(Path(plane.database.path).resolve()))


def enqueue_invalidations(store, c, belief_id, event_id):
    rows = c.execute(
        """SELECT e.* FROM execution_dependencies e JOIN execution_dependency_links l
        ON e.controller_ref=l.controller_ref AND e.organisation_id=l.organisation_id
        AND e.grant_id=l.grant_id WHERE l.belief_id=?""",
        (belief_id,),
    ).fetchall()
    for row in rows:
        changed = c.execute(
            """INSERT OR IGNORE INTO dependency_revocations
            (controller_ref,organisation_id,grant_id,operation_id,trigger_event_id)
            VALUES(?,?,?,?,?)""",
            (
                row["controller_ref"],
                row["organisation_id"],
                row["grant_id"],
                row["operation_id"],
                event_id,
            ),
        ).rowcount
        if changed:
            store.event(
                c,
                "dependency_revocation_requested",
                {
                    "controller_ref": row["controller_ref"],
                    "organisation_id": row["organisation_id"],
                    "grant_id": row["grant_id"],
                    "operation_id": row["operation_id"],
                    "trigger_event_id": event_id,
                },
            )


def bind_dependencies(store, c, *, plane, plan, grant, operation_id, session):
    data = {
        "controller_ref": controller_reference(plane),
        "organisation_id": plan.organisation_id,
        "grant_id": grant.execution_grant_id,
        "grant_hash": grant.grant_hash,
        "operation_id": operation_id,
        "session": session,
        "plan_binding": digest(plan.model_dump()),
        "beliefs": list(plan.required_belief_ids),
    }
    existing = c.execute(
        """SELECT * FROM execution_dependencies
        WHERE controller_ref=? AND organisation_id=? AND grant_id=?""",
        (data["controller_ref"], data["organisation_id"], data["grant_id"]),
    ).fetchone()
    if existing:
        if json.loads(existing["binding_json"]) != data:
            raise ValueError("Native grant is already bound to another dependency operation")
        return
    for belief_id in data["beliefs"]:
        belief = c.execute(
            "SELECT status FROM beliefs WHERE id=? AND session=?", (belief_id, session)
        ).fetchone()
        if not belief or belief[0] != "active":
            raise ValueError("Cannot bind an inactive or cross-session belief")
    event_id = store.event(
        c,
        "execution_dependencies_bound",
        {
            "controller_ref": data["controller_ref"],
            "organisation_id": data["organisation_id"],
            "grant_id": data["grant_id"],
            "binding_commitment": digest(data),
        },
    )
    c.execute(
        "INSERT INTO execution_dependencies VALUES(?,?,?,?,?,?,?)",
        (
            data["controller_ref"],
            data["organisation_id"],
            data["grant_id"],
            operation_id,
            session,
            canonical(data),
            event_id,
        ),
    )
    for belief_id in set(data["beliefs"]):
        c.execute(
            "INSERT INTO execution_dependency_links VALUES(?,?,?,?)",
            (data["controller_ref"], data["organisation_id"], data["grant_id"], belief_id),
        )


def enrollment_anchor(store):
    """Retain the existing audit producer identity outside SQLite; never silently re-enroll."""
    marker = Path(store.path).with_name(Path(store.path).name + ".dependencies.json")
    with store.connection() as c:
        row = c.execute("SELECT source FROM delivery_meta WHERE singleton=1").fetchone()
        if not row:
            raise ValueError(
                "Authenticated audit enrollment required before dependency composition"
            )
        source = row[0]
        bound = c.execute("SELECT 1 FROM execution_dependencies LIMIT 1").fetchone()
    expected = canonical({"schema": "galaxy.dependencies.v1", "source": source})
    if marker.exists():
        info = marker.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > 4096 or marker.read_text() != expected:
            raise ValueError("Dependency store enrollment changed or is corrupt")
    else:
        if bound:
            raise ValueError("Existing dependency enrollment anchor is missing")
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            handle.write(expected)
            handle.flush()
            os.fsync(handle.fileno())
    return source, marker, expected


class DependencyAuthority:
    """Delegates all issuance/policy to JoyCtl; adds a veto, never an execution grant.

    Must be installed in the owning isolated controller before worker ingress.
    Read transactions see committed belief changes; running commands are not retroactively undone.
    """

    def __init__(self, delegate, store, reference, anchor):
        self.delegate, self.store_path, self.reference = delegate, store.path, reference
        self.source, self.marker, self.marker_content = anchor

    @contextmanager
    def read_store(self):
        # Never recreate a missing/corrupt store during an authorization check.
        uri = Path(self.store_path).resolve().as_uri() + "?mode=ro"
        c = sqlite3.connect(uri, uri=True, timeout=2, isolation_level=None)
        c.row_factory = sqlite3.Row
        try:
            c.execute("BEGIN")
            yield c
        finally:
            c.close()

    def verify_source(self, c):
        if not self.marker.is_file() or self.marker.read_text() != self.marker_content:
            raise ValueError("Dependency enrollment anchor unavailable")
        meta = c.execute("SELECT source FROM delivery_meta WHERE singleton=1").fetchone()
        if not meta or meta[0] != self.source:
            raise ValueError("Dependency database was replaced or re-enrolled")
        previous = "0" * 64
        for count, event in enumerate(c.execute("SELECT * FROM events ORDER BY id"), 1):
            if (
                count > 100000
                or event["previous"] != previous
                or event["hash"] != digest([event["kind"], event["payload"], previous])
            ):
                raise ValueError("Dependency audit integrity or verification budget failure")
            previous = event["hash"]

    def _check(self, organisation_id, grant, worker_authorization_id=None):
        from joyctl.runtime.hosted_verification import HostedVerificationError

        try:
            with self.read_store() as c:
                self.verify_source(c)
                row = c.execute(
                    """SELECT * FROM execution_dependencies WHERE controller_ref=?
                    AND organisation_id=? AND grant_id=?""",
                    (self.reference, organisation_id, grant.execution_grant_id),
                ).fetchone()
                if row is None:
                    # Unknown non-Galaxy grants retain native semantics, but deleted enrollment
                    # after binding is corruption rather than an unguarded grant.
                    recorded = c.execute(
                        """SELECT 1 FROM events WHERE kind='execution_dependencies_bound'
                        AND json_extract(payload,'$.controller_ref')=?
                        AND json_extract(payload,'$.organisation_id')=?
                        AND json_extract(payload,'$.grant_id')=?""",
                        (self.reference, organisation_id, grant.execution_grant_id),
                    ).fetchone()
                    if recorded:
                        raise ValueError("Missing dependency enrollment")
                    legacy = c.execute(
                        """SELECT 1 FROM integration_operations o
                        WHERE json_extract(o.plan,'$.organisation_id')=?
                        AND json_array_length(o.plan,'$.required_belief_ids')>0
                        AND (? IS NULL OR json_extract(o.plan,'$.authorization_id')=?)
                        AND NOT EXISTS(SELECT 1 FROM execution_dependencies e WHERE
                            e.operation_id=o.id AND e.controller_ref=?) LIMIT 1""",
                        (
                            organisation_id,
                            worker_authorization_id,
                            worker_authorization_id,
                            self.reference,
                        ),
                    ).fetchone()
                    if legacy:
                        raise ValueError(
                            "Legacy dependency operation requires explicit enrollment review"
                        )
                    return
                data = json.loads(row["binding_json"])
                if any(
                    data[k] != row[k]
                    for k in (
                        "controller_ref",
                        "organisation_id",
                        "grant_id",
                        "operation_id",
                        "session",
                    )
                ):
                    raise ValueError("Dependency binding mismatch")
                event = c.execute("SELECT * FROM events WHERE id=?", (row["event_id"],)).fetchone()
                if (
                    not event
                    or event["kind"] != "execution_dependencies_bound"
                    or json.loads(event["payload"]).get("binding_commitment") != digest(data)
                    or data["grant_hash"] != grant.grant_hash
                ):
                    raise ValueError("Dependency enrollment commitment mismatch")
                links = {
                    r[0]
                    for r in c.execute(
                        """SELECT belief_id FROM execution_dependency_links
                    WHERE controller_ref=? AND organisation_id=? AND grant_id=?""",
                        (self.reference, organisation_id, grant.execution_grant_id),
                    )
                }
                if links != set(data["beliefs"]):
                    raise ValueError("Dependency link projection mismatch")
                revoked = c.execute(
                    """SELECT 1 FROM dependency_revocations WHERE controller_ref=?
                    AND organisation_id=? AND grant_id=?""",
                    (self.reference, organisation_id, grant.execution_grant_id),
                ).fetchone()
                if revoked:
                    raise ValueError("Dependency revocation is pending or permanent")
                for belief_id in links:
                    belief = c.execute(
                        "SELECT status FROM beliefs WHERE id=? AND session=?",
                        (belief_id, row["session"]),
                    ).fetchone()
                    if not belief or belief[0] != "active":
                        raise ValueError("Required dependency is no longer active")
        except Exception as exc:
            raise HostedVerificationError(
                "Galaxy dependency validation denied or unavailable"
            ) from exc

    def validate(self, organisation_id, grant, *, worker_authorization_id=None):
        self.delegate.validate(
            organisation_id, grant, worker_authorization_id=worker_authorization_id
        )
        self._check(organisation_id, grant, worker_authorization_id)

    def store(self, organisation_id):
        return self.delegate.store(organisation_id)

    def register(self, organisation_id, grant, worker_authorization_id):
        result = self.delegate.register(organisation_id, grant, worker_authorization_id)
        self._check(organisation_id, grant)
        return result

    def revoke(self, organisation_id, grant_id, reason):
        return self.delegate.revoke(organisation_id, grant_id, reason)

    @contextmanager
    def completion_fence(self, organisation_id, grant):
        with self.delegate.completion_fence(organisation_id, grant):
            self.validate(organisation_id, grant)
            yield


def install_dependency_authority(plane, store):
    from joyctl.runtime.hosted_verification import HostedVerificationError

    if plane.config.mode != "local-development":
        raise HostedVerificationError(
            "Dependency composition is qualified only for isolated development"
        )
    current = plane.snapshot_grant_authority
    if current is None:
        raise HostedVerificationError("Existing native grant authority required")
    reference = controller_reference(plane)
    try:
        anchor = enrollment_anchor(store)
    except Exception as exc:
        raise HostedVerificationError(
            "Dependency enrollment unavailable; explicit recovery required"
        ) from exc
    if isinstance(current, DependencyAuthority):
        if (
            Path(current.store_path).resolve() != Path(store.path).resolve()
            or current.source != anchor[0]
        ):
            raise HostedVerificationError(
                "Controller already bound to a different dependency store"
            )
        if plane.snapshot_verifications.grant_authority is not current:
            raise HostedVerificationError("Native registry dependency composition was replaced")
        return current
    if plane.snapshot_verifications.grant_authority is not current:
        raise HostedVerificationError("Owning native authority/registry do not share one authority")
    guard = DependencyAuthority(current, store, reference, anchor)
    plane.snapshot_grant_authority = guard
    plane.snapshot_verifications.grant_authority = guard
    return guard


class RevocationDelivery:
    def __init__(self, store, guard, organisation_id):
        self.store, self.guard, self.organisation_id = store, guard, organisation_id

    def status(self):
        with self.guard.read_store() as c:
            self.guard.verify_source(c)
            rows = c.execute(
                """SELECT * FROM dependency_revocations WHERE controller_ref=?
                AND organisation_id=?""",
                (self.guard.reference, self.organisation_id),
            ).fetchall()
            for row in rows:
                if row["acknowledged"]:
                    ack = c.execute(
                        """SELECT 1 FROM events
                        WHERE kind='native_dependency_revocation_acknowledged'
                        AND json_extract(payload,'$.controller_ref')=?
                        AND json_extract(payload,'$.organisation_id')=?
                        AND json_extract(payload,'$.grant_id')=?
                        AND json_extract(payload,'$.trigger_event_id')=?""",
                        (
                            row["controller_ref"],
                            row["organisation_id"],
                            row["grant_id"],
                            row["trigger_event_id"],
                        ),
                    ).fetchone()
                    if not ack:
                        raise ValueError(
                            "Revocation acknowledgment has no audited native confirmation"
                        )
        total = len(rows)
        pending = sum(not row["acknowledged"] for row in rows)
        return {
            "requested": total,
            "pending": pending,
            "native_acknowledged": total - pending,
            "authority": "existing JoyCtl native grant store",
        }

    def validate_debt(self, row):
        with self.guard.read_store() as c:
            self.guard.verify_source(c)
            enrollment = c.execute(
                """SELECT * FROM execution_dependencies WHERE controller_ref=?
                AND organisation_id=? AND grant_id=?""",
                (row["controller_ref"], row["organisation_id"], row["grant_id"]),
            ).fetchone()
            if not enrollment or enrollment["operation_id"] != row["operation_id"]:
                raise ValueError("Revocation target lacks matching dependency enrollment")
            data = json.loads(enrollment["binding_json"])
            registered = c.execute(
                "SELECT * FROM events WHERE id=?", (enrollment["event_id"],)
            ).fetchone()
            trigger = c.execute(
                "SELECT * FROM events WHERE id=?", (row["trigger_event_id"],)
            ).fetchone()
            if (
                not registered
                or registered["kind"] != "execution_dependencies_bound"
                or json.loads(registered["payload"]).get("binding_commitment") != digest(data)
                or any(
                    data[k] != row[k]
                    for k in ("controller_ref", "organisation_id", "grant_id", "operation_id")
                )
                or not trigger
                or trigger["kind"] != "belief_revision"
            ):
                raise ValueError("Revocation registration or causal commitment mismatch")
            change = json.loads(trigger["payload"])
            if change["status"] == "active" or change["belief_id"] not in data["beliefs"]:
                raise ValueError("Revocation cause is not an invalidated required belief")
            requested = c.execute(
                """SELECT 1 FROM events WHERE kind='dependency_revocation_requested'
                AND json_extract(payload,'$.controller_ref')=?
                AND json_extract(payload,'$.organisation_id')=?
                AND json_extract(payload,'$.grant_id')=?
                AND json_extract(payload,'$.trigger_event_id')=?""",
                (
                    row["controller_ref"],
                    row["organisation_id"],
                    row["grant_id"],
                    row["trigger_event_id"],
                ),
            ).fetchone()
            if not requested:
                raise ValueError("Unaudited revocation request")

    def flush(self, *, limit=256, after_native_revoke=None):
        if not 1 <= limit <= 256:
            raise ValueError("Revocation delivery limit must be 1..256")
        from joyctl.schema_contracts import RevokedError

        with self.guard.read_store() as c:
            self.guard.verify_source(c)
            rows = c.execute(
                """SELECT * FROM dependency_revocations WHERE acknowledged=0
                AND controller_ref=? AND organisation_id=? ORDER BY trigger_event_id LIMIT ?""",
                (self.guard.reference, self.organisation_id, limit),
            ).fetchall()
        errors = []
        for row in rows:
            try:
                self.validate_debt(row)
                self.guard.delegate.revoke(
                    row["organisation_id"], row["grant_id"], "Galaxy required belief invalidated"
                )
                try:
                    self.guard.delegate.store(row["organisation_id"]).lookup_grant(row["grant_id"])
                except RevokedError:
                    pass
                else:
                    raise RuntimeError("Native revocation was not established")
                if after_native_revoke:
                    after_native_revoke()
                with self.store.connection() as c:
                    updated = c.execute(
                        """UPDATE dependency_revocations SET acknowledged=1,
                        attempts=attempts+1,error_type=NULL WHERE controller_ref=?
                        AND organisation_id=? AND grant_id=? AND acknowledged=0""",
                        (row["controller_ref"], row["organisation_id"], row["grant_id"]),
                    ).rowcount
                    if updated:
                        self.store.event(
                            c,
                            "native_dependency_revocation_acknowledged",
                            {
                                "controller_ref": row["controller_ref"],
                                "organisation_id": row["organisation_id"],
                                "grant_id": row["grant_id"],
                                "operation_id": row["operation_id"],
                                "trigger_event_id": row["trigger_event_id"],
                            },
                        )
            except Exception as exc:  # noqa: BLE001 -- preserve pending debt, never acknowledge an outage
                errors.append(type(exc).__name__)
                with self.store.connection() as c:
                    c.execute(
                        """UPDATE dependency_revocations SET attempts=attempts+1,error_type=?
                        WHERE controller_ref=? AND organisation_id=? AND grant_id=?""",
                        (
                            type(exc).__name__,
                            row["controller_ref"],
                            row["organisation_id"],
                            row["grant_id"],
                        ),
                    )
                    self.store.event(
                        c,
                        "native_dependency_revocation_unavailable",
                        {
                            "grant_id": row["grant_id"],
                            "operation_id": row["operation_id"],
                            "error_type": type(exc).__name__,
                        },
                    )
        return {**self.status(), "errors": errors}
