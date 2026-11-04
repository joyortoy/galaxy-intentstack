"""Transactional forwarding into the existing JoyEvidence authenticated ledger."""

import json
import uuid
from datetime import UTC, datetime

from .audit import canonical


def enqueue(c, row):
    meta = c.execute("SELECT * FROM delivery_meta WHERE singleton=1").fetchone()
    if not meta:
        return
    envelope = {
        "schema": "joy.evidence.v1",
        "event_id": str(row["id"]),
        "source": meta["source"],
        "user_id": meta["user_id"],
        "actor_id": meta["actor_id"],
        "action": row["kind"],
        "scope": "deep",
        "entity": {"type": "galaxy-event", "local_id": str(row["id"])},
        "revision": row["id"],
        "payload_commitment": row["hash"],
        "details": {"method": "local-predecessor:" + row["previous"], "count": row["id"]},
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    c.execute(
        "INSERT OR IGNORE INTO audit_outbox(event_id,envelope) VALUES(?,?)",
        (row["id"], canonical(envelope)),
    )


class AuditDelivery:
    def __init__(self, store, ledger, *, user_id, actor_id):
        # ledger must be the existing joyevidence.Ledger, or a failure-injection proxy in tests.
        self.store, self.ledger = store, ledger
        with store.connection() as c:
            prior = c.execute("SELECT * FROM delivery_meta").fetchone()
            if prior and (prior["user_id"] != user_id or prior["actor_id"] != actor_id):
                raise ValueError("Audit enrollment identity cannot change")
            if not prior:
                c.execute(
                    "INSERT INTO delivery_meta VALUES(1,?,?,?)",
                    ("galaxy:" + str(uuid.uuid4()), user_id, actor_id),
                )
            for row in c.execute("SELECT * FROM events ORDER BY id").fetchall():
                enqueue(c, row)

    def flush(self, *, limit=256, after_append=None):
        if not 1 <= limit <= 256:
            raise ValueError("Delivery limit must be 1..256")
        if not self.store.verify_audit():
            raise RuntimeError("Local audit corruption")
        self.ledger.verify()
        with self.store.connection() as c:
            rows = c.execute(
                "SELECT * FROM audit_outbox WHERE acknowledged=0 ORDER BY event_id LIMIT ?",
                (limit,),
            ).fetchall()
        for row in rows:
            event = json.loads(row["envelope"])
            # Validate against current local commitment before handing it to a signing authority.
            with self.store.connection() as c:
                local = c.execute("SELECT * FROM events WHERE id=?", (row["event_id"],)).fetchone()
                meta = c.execute("SELECT * FROM delivery_meta").fetchone()
                if (
                    not local
                    or event["source"] != meta["source"]
                    or event["event_id"] != str(local["id"])
                    or event["payload_commitment"] != local["hash"]
                    or event["user_id"] != meta["user_id"]
                    or event["actor_id"] != meta["actor_id"]
                    or event["action"] != local["kind"]
                    or event["details"]
                    != {"method": "local-predecessor:" + local["previous"], "count": local["id"]}
                ):
                    raise RuntimeError("Outbox commitment or identity mismatch")
            from joyevidence import digest

            receipt = self.ledger.append(event)
            if receipt.get("event_digest") != digest(event):
                raise RuntimeError("Sink acknowledgment does not match envelope")
            self.ledger.verify()
            if after_append:
                after_append()
            with self.store.connection() as c:
                c.execute(
                    "UPDATE audit_outbox SET acknowledged=1,receipt=? WHERE event_id=?",
                    (canonical(receipt), row["event_id"]),
                )
        return self.status()

    def status(self):
        with self.store.connection() as c:
            total, pending = c.execute(
                "SELECT count(*),coalesce(sum(acknowledged=0),0) FROM audit_outbox"
            ).fetchone()
        return {
            "local_persisted": total,
            "sink_acknowledged": total - pending,
            "pending": pending,
            "sink": "existing_local_joyevidence_hmac_ledger",
            "remote_acknowledged": False,
        }

    def require_current(self):
        # Bounded flush: never silently ignore a backlog larger than one batch.
        result = self.flush()
        if result["pending"]:
            raise RuntimeError("Authenticated audit delivery backlog remains")
        # An acknowledgment flag alone is not authenticated evidence. Verify every acknowledged
        # envelope against the real sink record after the sink's HMAC/checkpoint verification.
        from joyevidence import digest

        with self.store.connection() as c:
            acknowledged = c.execute("SELECT * FROM audit_outbox WHERE acknowledged=1").fetchall()
        with self.ledger.connection() as sink:
            for row in acknowledged:
                event = json.loads(row["envelope"])
                stored = sink.execute(
                    "SELECT event_digest FROM records WHERE source=? AND event_id=?",
                    (event["source"], event["event_id"]),
                ).fetchone()
                if not stored or stored[0] != digest(event):
                    raise RuntimeError("Local acknowledgment lacks authenticated sink evidence")
        return result
