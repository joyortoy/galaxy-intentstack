"""Trusted-host authority only. Never import permissions from message or memory fields."""
import hashlib
import json
import secrets
import uuid

from .audit import canonical, digest
from .models import Authorization


class Authority:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def enroll(self, principal, token, capabilities=()):
        if len(token) < 32 or not principal:
            raise ValueError("Nonempty identity and at least 32 token characters required")
        with self.store.connection() as c:
            c.execute("INSERT INTO principals VALUES(?,?,?,1)",
                      (principal, hashlib.sha256(token.encode()).hexdigest(), canonical(capabilities)))
            self.store.event(c, "principal_enrolled", {"principal": principal})

    def authenticate(self, c, token):
        if not token:
            return None
        hashed = hashlib.sha256(token.encode()).hexdigest()
        for row in c.execute("SELECT * FROM principals WHERE active=1"):
            if secrets.compare_digest(row["token_hash"], hashed):
                return row
        return None

    def grant(self, principal, action, session, *, starts=None, expires, approval_required=False):
        if expires <= (self.clock() if starts is None else starts):
            raise ValueError("Invalid grant validity period")
        grant_id = str(uuid.uuid4())
        with self.store.connection() as c:
            if not c.execute("SELECT 1 FROM principals WHERE id=? AND active=1",
                             (principal,)).fetchone():
                raise ValueError("Unknown or inactive principal")
            c.execute("INSERT INTO grants VALUES(?,?,?,?,?,?,?,?,?,0)",
                      (grant_id, principal, action.kind, action.resource, action.scope, session,
                       self.clock() if starts is None else starts, expires, int(approval_required)))
            self.store.event(c, "grant_created", {"grant_id": grant_id, "principal": principal,
                                                "binding": digest([action.model_dump(), session])})
        return grant_id

    def approve(self, grant_id, token, expires):
        with self.store.connection() as c:
            p = self.authenticate(c, token)
            grant = c.execute("SELECT * FROM grants WHERE id=?", (grant_id,)).fetchone()
            if not p or "approve" not in json.loads(p["capabilities"]) or not grant:
                raise PermissionError("Authenticated approver capability required")
            if p["id"] == grant["principal"] or expires <= self.clock():
                raise PermissionError("Separate approver and unexpired approval required")
            c.execute("INSERT OR REPLACE INTO approvals VALUES(?,?,?)",
                      (grant_id, p["id"], min(expires, grant["expires"])))
            self.store.event(c, "approval_recorded", {"grant_id": grant_id, "approver": p["id"]})

    def revoke(self, grant_id):
        with self.store.connection() as c:
            if c.execute("UPDATE grants SET revoked=1 WHERE id=?", (grant_id,)).rowcount != 1:
                raise ValueError("Unknown grant")
            self.store.event(c, "grant_revoked", {"grant_id": grant_id})

    def disable_principal(self, principal):
        with self.store.connection() as c:
            c.execute("UPDATE principals SET active=0 WHERE id=?", (principal,))
            self.store.event(c, "principal_disabled", {"principal": principal})

    def set_policy(self, enabled):
        with self.store.connection() as c:
            c.execute("UPDATE policy SET enabled=? WHERE singleton=1", (int(enabled),))
            self.store.event(c, "policy_changed", {"enabled": bool(enabled)})

    def check(self, c, action, session, token):
        p = self.authenticate(c, token)
        if not p:
            return Authorization(allowed=False, reason="Unauthenticated principal")
        base = {"principal": p["id"]}
        if action is None:
            return Authorization(allowed=False, reason="No explicit action request", **base)
        if not c.execute("SELECT enabled FROM policy").fetchone()[0]:
            return Authorization(allowed=False, reason="Policy disabled", **base)
        for belief_id in action.belief_ids:
            b = c.execute("SELECT * FROM beliefs WHERE id=? AND session=?",
                          (belief_id, session)).fetchone()
            if not b or b["status"] != "active":
                return Authorization(allowed=False, reason="Missing or invalidated belief", **base)
            claim = c.execute("SELECT data FROM claims WHERE id=?", (b["claim_id"],)).fetchone()
            if not claim or json.loads(claim[0])["state"] != "VERIFIED":
                return Authorization(allowed=False, reason="Required belief is not verified", **base)
        grants = c.execute("""SELECT * FROM grants WHERE principal=? AND kind=? AND resource=?
            AND scope=? AND session=? AND revoked=0 AND starts<=? AND expires>?""",
            (p["id"], action.kind, action.resource, action.scope, session,
             self.clock(), self.clock())).fetchall()
        pending = False
        for g in grants:
            if g["approval"]:
                approval = c.execute("""SELECT a.* FROM approvals a JOIN principals p
                    ON a.approver=p.id WHERE a.grant_id=? AND a.expires>? AND p.active=1""",
                    (g["id"], self.clock())).fetchone()
                if not approval:
                    pending = True
                    continue
            return Authorization(allowed=True, reason="Exact scoped permission is current",
                                 grant_id=g["id"], **base)
        return Authorization(allowed=False,
                             reason="Human approval required" if pending else
                                    "No current permission for exact action, resource, scope and session",
                             approval_required=pending, **base)
