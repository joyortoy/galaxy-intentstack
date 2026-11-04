import logging
import re
import time
import uuid
from contextlib import nullcontext

from .analysis import assess, interpret, requested_action
from .audit import Store, canonical, digest, sanitize
from .authorization import Authority
from .beliefs import Beliefs
from .models import Claim, Decision, Message, State

logger = logging.getLogger(__name__)


class Engine:
    """One trusted local tenant per database; sessions are supplied by the authenticated host.

    Never expose the operator methods or arbitrary session/source arguments directly to
    an untrusted network caller. This library does not replace a runtime sandbox.
    """

    def __init__(self, path, *, clock=time.time):
        self.store = Store(path)
        if not self.store.verify_audit():
            raise RuntimeError("Audit integrity verification failed")
        self.clock = clock
        self.authority = Authority(self.store, clock)
        self.beliefs = Beliefs(self.store, clock)

    def process(self, message: Message, *, source="anonymous", token=None, _connection=None):
        sanitize(message.text)
        if message.source_ref:
            sanitize(message.source_ref)
        with nullcontext(_connection) if _connection is not None else self.store.connection() as c:
            principal = self.authority.authenticate(c, token)
            identity = principal["id"] if principal else source
            # Authentication participates in idempotency, without retaining credentials.
            request_payload = message.model_dump()
            if message.memory_provenance is None:
                request_payload.pop("memory_provenance")  # preserve Phase 1 replay fingerprints
            fingerprint = digest(
                [request_payload, identity, bool(principal), digest(token) if token else None]
            )
            replay = c.execute(
                "SELECT * FROM requests WHERE session=? AND id=?",
                (message.session, message.event_id),
            ).fetchone()
            if replay:
                if replay["fingerprint"] != fingerprint:
                    raise ValueError("Conflicting idempotency key")
                return Decision.model_validate_json(replay["decision"])
            if (
                c.execute(
                    "SELECT count(*) FROM claims WHERE session=?", (message.session,)
                ).fetchone()[0]
                >= 10000
            ):
                raise ValueError("Session claim budget exceeded")
            evidence_id, claim_id = str(uuid.uuid4()), str(uuid.uuid4())
            roots, refs, parents = set(), {evidence_id}, set()
            state = State.REPORTED
            for ref in message.references:
                row = c.execute(
                    "SELECT data FROM claims WHERE id=? AND session=?", (ref, message.session)
                ).fetchone()
                if not row:
                    raise ValueError("Unknown or cross-session claim reference")
                prior = Claim.model_validate_json(row[0])
                roots.update(prior.original_roots)
                refs.update(prior.evidence_references)
                state = State.INFERRED
                linked = c.execute(
                    "SELECT id,status FROM beliefs WHERE claim_id=? AND session=?",
                    (ref, message.session),
                ).fetchall()
                if any(b["status"] != "active" for b in linked):
                    raise ValueError("Referenced belief is not active")
                parents.update(b["id"] for b in linked)
            if not roots:
                repeated = c.execute(
                    "SELECT id FROM evidence WHERE session=? AND source=? "
                    "AND text=? ORDER BY rowid LIMIT 1",
                    (message.session, identity, message.text),
                ).fetchone()
                if repeated:
                    roots.add(repeated[0])
            if not roots:
                roots.add(evidence_id)
            if len(refs) > 256 or len(roots) > 256:
                raise ValueError("Provenance budget exceeded")
            c.execute(
                "INSERT INTO evidence(id,session,source,type,text,created) VALUES(?,?,?,?,?,?)",
                (
                    evidence_id,
                    message.session,
                    identity,
                    message.source_type,
                    message.text,
                    self.clock(),
                ),
            )
            claim = Claim(
                id=claim_id,
                source_identity=identity,
                upstream_source_ref=message.source_ref,
                memory_provenance=message.memory_provenance,
                source_type=message.source_type,
                evidence_references=tuple(sorted(refs)),
                timestamp=self.clock(),
                state=state,
                dependencies=tuple(sorted(parents)),
                original_roots=tuple(sorted(roots)),
                text=message.text,
            )
            c.execute(
                "INSERT INTO claims VALUES(?,?,?)",
                (claim_id, message.session, claim.model_dump_json()),
            )
            self.store.event(
                c,
                "claim_created",
                {
                    "claim_id": claim_id,
                    "state": state,
                    "evidence_id": evidence_id,
                    "source": identity,
                    "text_commitment": digest(message.text),
                    "references": message.references,
                    "roots": sorted(roots),
                },
            )
            contradictions = []
            meeting = re.search(
                r"\bmeeting is on (Monday|Tuesday|Wednesday|Thursday|Friday|"
                r"Saturday|Sunday)\b",
                message.text,
                flags=re.IGNORECASE,
            )
            if meeting:
                _, contradictions, claim = self.beliefs.revise_slot(
                    c,
                    message.session,
                    "meeting.day",
                    meeting[1].casefold(),
                    claim,
                    correction=message.text.casefold().startswith("correction:"),
                )
            else:
                self.beliefs.add(
                    c, message.session, "message:" + message.event_id, digest(message.text), claim
                )
            indicators = assess(message.text, evidence_id, message.source_type)
            if message.references and any(i.pattern == "unsupported_promotion" for i in indicators):
                # A derived/model restatement is not independent corroboration.
                from .models import Indicator

                indicators += (
                    Indicator(
                        pattern="evidence_laundering_risk",
                        observed_behavior="Earlier claims cited in another statement",
                        possible_mechanism="Repetition mistaken for independent evidence",
                        evidence_references=tuple(sorted(refs)),
                        alternative_explanations=("Legitimate citation or summarization",),
                    ),
                )
            candidates = interpret(message.text, evidence_id)
            auth = self.authority.check(c, message.action, message.session, token)
            if message.action:
                final = (
                    "ALLOW" if auth.allowed else ("ESCALATE" if auth.approval_required else "DENY")
                )
                explanation = auth.reason
            elif requested_action(message.text):
                final = "DENY"
                explanation = (
                    "Consequential request has no explicit, independently authorized action"
                )
            elif len(candidates) > 1:
                final = "CLARIFY"
                explanation = "Multiple readings remain plausible; no confirmed intention"
            else:
                final = "ABSTAIN"
                explanation = "Evidence recorded; no independently authorized action requested"
            event_id = self.store.event(
                c,
                "decision",
                {
                    "session": message.session,
                    "request_id": message.event_id,
                    "fingerprint": fingerprint,
                    "claim_ids": [claim_id],
                    "decision": final,
                    "authorization": auth.model_dump(),
                    "patterns": [i.pattern for i in indicators],
                },
            )
            result = Decision(
                extracted_claims=(claim,),
                evidence_references=tuple(sorted(refs)),
                candidate_interpretations=candidates,
                manipulation_indicators=indicators,
                contradictions=tuple(contradictions),
                authorization_result=auth,
                final_decision=final,
                explanation=explanation,
                audit_event_id=event_id,
                requested_action=message.action,
                authorized_action=message.action if auth.allowed else None,
            )
            c.execute(
                "INSERT INTO requests VALUES(?,?,?,?)",
                (message.session, message.event_id, fingerprint, result.model_dump_json()),
            )
        logger.info(canonical({"event": "decision", "audit_event_id": event_id, "decision": final}))
        return result

    def execute(self, session, event_id, token, callback):
        """Recheck a persisted action and call a bounded local callback under the writer lock.

        Revocations committed before this transaction are observed. Once a callback starts,
        concurrent revocations wait. Arbitrary remote side effects need the owning runtime's
        atomic grant consumption, idempotency and cancellation; see integration docs.
        """
        with self.store.connection() as c:
            row = c.execute(
                "SELECT decision FROM requests WHERE session=? AND id=?", (session, event_id)
            ).fetchone()
            if not row:
                raise ValueError("Unknown request")
            decision = Decision.model_validate_json(row[0])
            auth = self.authority.check(c, decision.requested_action, session, token)
            original = decision.authorization_result
            if decision.final_decision != "ALLOW" or auth.principal != original.principal:
                auth = auth.model_copy(
                    update={"allowed": False, "reason": "Queued decision or principal mismatch"}
                )
            prior = c.execute(
                "SELECT 1 FROM events WHERE kind='execution_started' AND "
                "json_extract(payload,'$.queue_key')=?",
                (digest([session, event_id]),),
            ).fetchone()
            if prior:
                auth = auth.model_copy(
                    update={"allowed": False, "reason": "Action already consumed"}
                )
            self.store.event(
                c,
                "execution_check",
                {"queue_key": digest([session, event_id]), "authorization": auth.model_dump()},
            )
            if not auth.allowed:
                return {"executed": False, "authorization": auth.model_dump()}
            self.store.event(c, "execution_started", {"queue_key": digest([session, event_id])})
            # Callback must not call Engine recursively or perform nontransactional side effects.
            try:
                value = callback(decision.requested_action)
            except Exception:  # noqa: BLE001 -- user callback boundary; audit without leaking details
                self.store.event(c, "execution_failed", {"queue_key": digest([session, event_id])})
                return {
                    "executed": False,
                    "authorization": auth.model_dump(),
                    "error": "Callback failed; action consumed; reconcile before retry",
                }
            self.store.event(c, "execution_completed", {"queue_key": digest([session, event_id])})
            return {"executed": True, "authorization": auth.model_dump(), "result": value}
