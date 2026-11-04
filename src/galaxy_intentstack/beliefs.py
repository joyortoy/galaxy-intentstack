"""Local advisory graph, separate from IntentStack canonical memory."""
import json
import uuid

from .audit import canonical, digest
from .models import Claim, State


class Beliefs:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def invalidate(self, c, belief_id, reason, status="stale"):
        pending, seen = [(belief_id, status)], set()
        while pending:
            current, new_status = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            if len(seen) > 10000:
                raise ValueError("Dependency invalidation budget exceeded")
            old = c.execute("SELECT * FROM beliefs WHERE id=?", (current,)).fetchone()
            if not old:
                raise ValueError("Unknown belief")
            c.execute("UPDATE beliefs SET status=?,revision=revision+1 WHERE id=?",
                      (new_status, current))
            self.store.event(c, "belief_revision", {"belief_id": current, "previous": dict(old),
                                                  "status": new_status, "reason": reason})
            pending.extend((r[0], "stale") for r in c.execute(
                "SELECT child FROM edges WHERE parent=?", (current,)))
        return seen

    def add(self, c, session, subject, value, claim):
        # Fresh nodes only: cycles cannot be introduced through this interface.
        belief_id = str(uuid.uuid4())
        c.execute("INSERT INTO beliefs VALUES(?,?,?,?,?,'active',1,?,?)",
                  (belief_id, session, subject, value, claim.id,
                   claim.source_identity, self.clock()))
        for parent in claim.dependencies:
            b = c.execute("SELECT status FROM beliefs WHERE id=? AND session=?",
                          (parent, session)).fetchone()
            if not b or b[0] != "active":
                raise ValueError("Dependency missing, stale, or outside session")
            c.execute("INSERT INTO edges VALUES(?,?)", (parent, belief_id))
        self.store.event(c, "belief_created", {"belief_id": belief_id, "claim_id": claim.id,
                                              "subject": digest(subject), "value": digest(value),
                                              "dependencies": claim.dependencies})
        return belief_id

    def revise_slot(self, c, session, subject, value, claim, correction=False):
        previous = c.execute("""SELECT * FROM beliefs WHERE session=? AND subject=?
                            AND status IN ('active','disputed')""", (session, subject)).fetchall()
        conflicts = []
        source = c.execute("SELECT * FROM sources WHERE id=?", (claim.source_identity,)).fetchone()
        for old in previous:
            if old["value"] == value:
                continue
            old_source = c.execute("SELECT * FROM sources WHERE id=?", (old["source"],)).fetchone()
            justified = bool(correction and source and source["trusted"] and old_source
                             and (old["source"] == claim.source_identity
                                  or source["authority"] > old_source["authority"])
                             and claim.timestamp >= old["created"])
            self.invalidate(c, old["id"], "correction" if justified else "unresolved contradiction",
                            "superseded" if justified else "disputed")
            conflicts.append({"previous_belief_id": old["id"], "claim_id": old["claim_id"],
                              "new_claim_id": claim.id, "resolution":
                              "authorized_source_correction" if justified else "unresolved"})
            if not justified:
                old_claim = Claim.model_validate_json(c.execute(
                    "SELECT data FROM claims WHERE id=?", (old["claim_id"],)).fetchone()[0])
                self.update_claim(c, old_claim.model_copy(update={"state": State.DISPUTED}))
        belief_id = self.add(c, session, subject, value, claim)
        if any(x["resolution"] == "unresolved" for x in conflicts):
            self.invalidate(c, belief_id, "unresolved contradiction", "disputed")
            claim = claim.model_copy(update={"state": State.DISPUTED})
            self.update_claim(c, claim)
        return belief_id, conflicts, claim

    def update_claim(self, c, claim):
        c.execute("UPDATE claims SET data=? WHERE id=?", (claim.model_dump_json(), claim.id))
        self.store.event(c, "claim_revision", {"claim_id": claim.id, "state": claim.state,
                                              "validity": claim.validity,
                                              "verification_method": digest(claim.verification_method)})

    def retract(self, evidence_id):
        with self.store.connection() as c:
            if c.execute("UPDATE evidence SET valid=0 WHERE id=?", (evidence_id,)).rowcount != 1:
                raise ValueError("Unknown evidence")
            for row in c.execute("SELECT data FROM claims").fetchall():
                claim = Claim.model_validate_json(row[0])
                if evidence_id not in claim.evidence_references:
                    continue
                self.update_claim(c, claim.model_copy(update={"validity": "retracted",
                                                              "state": State.REFUTED}))
                for b in c.execute("SELECT id FROM beliefs WHERE claim_id=?", (claim.id,)).fetchall():
                    self.invalidate(c, b[0], "evidence retracted", "invalid")
            self.store.event(c, "evidence_retracted", {"evidence_id": evidence_id})

    def source_trust(self, source, *, authority=0, trusted=False):
        with self.store.connection() as c:
            c.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?)",
                      (source, authority, int(trusted)))
            if not trusted:
                for row in c.execute("SELECT id FROM beliefs WHERE source=?", (source,)).fetchall():
                    self.invalidate(c, row[0], "source trust withdrawn")
            self.store.event(c, "source_trust_changed", {"source": source, "authority": authority,
                                                       "trusted": trusted})

    def verify(self, claim_id, method, token, authority):
        if not method.strip() or len(method) > 300:
            raise ValueError("Bounded verification method required")
        with self.store.connection() as c:
            p = authority.authenticate(c, token)
            if not p or "verify" not in json.loads(p["capabilities"]):
                raise PermissionError("Independent verifier capability required")
            row = c.execute("SELECT data FROM claims WHERE id=?", (claim_id,)).fetchone()
            if not row:
                raise ValueError("Unknown claim")
            claim = Claim.model_validate_json(row[0])
            if claim.source_identity == p["id"] or claim.validity != "active":
                raise PermissionError("Independent verifier and valid evidence required")
            if claim.state in (State.DISPUTED, State.REFUTED):
                raise ValueError("Resolve contradiction before verification")
            self.update_claim(c, claim.model_copy(update={
                "state": State.VERIFIED, "verification_method": method}))

    def derive(self, session, text, parents):
        if not parents or len(parents) > 32:
            raise ValueError("Derived beliefs require 1..32 dependencies")
        with self.store.connection() as c:
            roots, references = set(), set()
            for parent in parents:
                row = c.execute("""SELECT c.data FROM beliefs b JOIN claims c ON b.claim_id=c.id
                              WHERE b.id=? AND b.session=? AND b.status='active'""",
                                (parent, session)).fetchone()
                if not row:
                    raise ValueError("Invalid dependency")
                claim = Claim.model_validate_json(row[0])
                roots.update(claim.original_roots)
                references.update(claim.evidence_references)
            claim = Claim(id=str(uuid.uuid4()), source_identity="local-inference",
                          source_type="derived", evidence_references=tuple(sorted(references)),
                          timestamp=self.clock(), state=State.INFERRED, dependencies=tuple(parents),
                          original_roots=tuple(sorted(roots)), text=text)
            c.execute("INSERT INTO claims VALUES(?,?,?)", (claim.id, session, claim.model_dump_json()))
            return self.add(c, session, "derived", digest(text), claim)

    def snapshot(self, session):
        with self.store.connection() as c:
            return [dict(r) for r in c.execute("SELECT * FROM beliefs WHERE session=?", (session,))]
