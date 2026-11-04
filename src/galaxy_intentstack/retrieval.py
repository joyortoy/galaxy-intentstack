"""Real IntentStack DataAgent boundary; snapshots are advisory evidence, not canonical memory."""

import json

from .audit import canonical, digest
from .models import Claim, Decision, MemoryProvenance, Message


class IntentStackRetrieval:
    def __init__(self, engine, agent, *, endpoint_id, user_id):
        self.engine, self.agent = engine, agent
        self.endpoint_id, self.user_id = endpoint_id, user_id

    def retrieve(self, *, request_id, session, query, limit=3, after_persist=None):
        if not 1 <= limit <= 5 or not 1 <= len(query.strip()) <= 1000:
            raise ValueError("Preserve IntentStack query and result limits")
        binding = digest([self.endpoint_id, self.user_id, session, query, limit])
        with self.engine.store.connection() as c:
            prior = c.execute(
                "SELECT * FROM retrieval_snapshots WHERE session=? AND request_id=?",
                (session, request_id),
            ).fetchone()
        if prior:
            if prior["binding"] != binding:
                raise ValueError("Conflicting retrieval replay")
        else:
            result = self.agent.retrieve(
                query, limit=limit, include_evidence=True, require_recorded=True
            )
            self._validate(result, limit)
            encoded = canonical(result)
            if len(encoded.encode()) > 524288:
                raise ValueError("Retrieval snapshot too large")
            with self.engine.store.connection() as c:
                existing = c.execute(
                    "SELECT * FROM retrieval_snapshots WHERE session=? AND request_id=?",
                    (session, request_id),
                ).fetchone()
                if existing and existing["binding"] != binding:
                    raise ValueError("Conflicting concurrent retrieval")
                if not existing:
                    c.execute(
                        "INSERT INTO retrieval_snapshots VALUES(?,?,?,?,?)",
                        (session, request_id, binding, encoded, digest(result)),
                    )
                    self.engine.store.event(
                        c,
                        "retrieval_captured",
                        {
                            "session": session,
                            "request_id": request_id,
                            "commitment": digest(result),
                            "binding": binding,
                        },
                    )
            if after_persist:
                after_persist()
        return self.replay(request_id=request_id, session=session)

    def _validate(self, result, limit):
        if (
            result.get("schema") != "intentstack.retrieval.v1"
            or not result.get("complete")
            or not result.get("evidence_requested")
            or len(result.get("items", [])) > limit
        ):
            raise ValueError("Complete recorded retrieval evidence required")
        for item in result["items"]:
            memory, citation, proof = item["memory"], item["citation"], item["evidence"]
            if (
                item["trust"] != "UNTRUSTED_CONTEXT"
                or memory["user_id"] != self.user_id
                or citation["memory_id"] != memory["id"]
                or citation["revision"] != memory["revision"]
                or citation["source_ref"] != memory["source_ref"]
                or proof["status"] != "RETURNED_REVISION_RECORDED"
                or not proof["complete"]
            ):
                raise ValueError("Retrieval identity/revision proof mismatch")
            from joyevidence import digest as upstream_digest

            expected = upstream_digest(
                {key: memory[key] for key in ("text", "status", "source_ref", "reason")}
            )
            support = proof.get("support", [])
            if (
                not support
                or any(s["payload_commitment"] != expected for s in support)
                or {s["ref"]["source_system"] for s in support}
                != {"intentstack-outbox", "joyevidence-ledger"}
            ):
                raise ValueError("Exact memory revision commitment required")

    def replay(self, *, request_id, session, after_import=None):
        # No network or wall-clock input: exact snapshots replay deterministically.
        with self.engine.store.connection() as c:
            row = c.execute(
                "SELECT * FROM retrieval_snapshots WHERE session=? AND request_id=?",
                (session, request_id),
            ).fetchone()
            if not row:
                raise ValueError("Missing retrieval snapshot")
            result = json.loads(row["payload"])
            if digest(result) != row["commitment"]:
                raise ValueError("Persisted retrieval snapshot corrupted")
            self._validate(result, 5)
            decisions = []
            # Import all items atomically. Newer revisions first are never rolled back by older ones.
            for item in sorted(
                result["items"],
                key=lambda x: (
                    x["memory"]["updated_at"],
                    x["memory"]["id"],
                    x["memory"]["revision"],
                ),
            ):
                m = item["memory"]
                event_id = digest([self.endpoint_id, self.user_id, m["id"], m["revision"]])
                imported = c.execute(
                    "SELECT decision FROM requests WHERE session=? AND id=?", (session, event_id)
                ).fetchone()
                if imported:
                    decisions.append(Decision.model_validate_json(imported[0]))
                    continue
                prior = c.execute(
                    "SELECT * FROM memory_versions WHERE endpoint=? AND user_id=? "
                    "AND session=? AND memory_id=? ORDER BY revision DESC LIMIT 1",
                    (self.endpoint_id, self.user_id, session, m["id"]),
                ).fetchone()
                if prior and prior["revision"] > m["revision"]:
                    raise ValueError("Older uncaptured revision cannot replace current memory")
                if prior:
                    old = Claim.model_validate_json(
                        c.execute(
                            "SELECT data FROM claims WHERE id=?", (prior["claim_id"],)
                        ).fetchone()[0]
                    )
                    self.engine.beliefs.update_claim(
                        c, old.model_copy(update={"validity": "superseded"})
                    )
                    for b in c.execute(
                        "SELECT id FROM beliefs WHERE claim_id=?", (prior["claim_id"],)
                    ).fetchall():
                        self.engine.beliefs.invalidate(
                            c, b[0], "upstream memory revision", "superseded"
                        )
                provenance = MemoryProvenance(
                    store_id=self.endpoint_id,
                    user_id=self.user_id,
                    actor_id=m["actor_id"],
                    memory_id=m["id"],
                    revision=m["revision"],
                    created_at=m["created_at"],
                    updated_at=m["updated_at"],
                    upstream_status=m["status"],
                    revision_recorded=True,
                )
                message = Message(
                    event_id=event_id,
                    session=session,
                    text=m["text"],
                    source_type="memory",
                    source_ref=m["source_ref"],
                    memory_provenance=provenance,
                )
                decision = self.engine.process(
                    message, source=self.endpoint_id + ":" + m["actor_id"], _connection=c
                )
                c.execute(
                    "INSERT INTO memory_versions VALUES(?,?,?,?,?,?)",
                    (
                        self.endpoint_id,
                        self.user_id,
                        session,
                        m["id"],
                        m["revision"],
                        decision.extracted_claims[0].id,
                    ),
                )
                decisions.append(decision)
                if after_import:
                    after_import()
            return decisions
