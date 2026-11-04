import sqlite3

import pytest
from conftest import REVIEWER, TOKEN, send
from pydantic import ValidationError

from galaxy_intentstack import Action, Message, State


@pytest.mark.parametrize(
    "change", [{"kind": "delete"}, {"resource": "meeting:2"}, {"scope": "admin"}]
)
def test_exact_permission_binding(engine, action, change):
    engine.authority.grant("user", action, "s", expires=2000)
    changed = Action.model_validate({**action.model_dump(), **change})
    assert send(engine, "please", action=changed, token=TOKEN).final_decision == "DENY"


@pytest.mark.parametrize("starts,expires", [(1100, 2000), (0, 999)])
def test_validity_period(engine, action, starts, expires):
    engine.authority.grant("user", action, "s", starts=starts, expires=expires)
    assert send(engine, "please", action=action, token=TOKEN).final_decision == "DENY"


def test_grants_are_session_scoped(engine, action):
    engine.authority.grant("user", action, "other-session", expires=2000)
    assert send(engine, "please", action=action, token=TOKEN).final_decision == "DENY"


def test_independent_approval_and_revocation(engine, action):
    g = engine.authority.grant("user", action, "s", expires=2000, approval_required=True)
    assert send(engine, "please", action=action, token=TOKEN).final_decision == "ESCALATE"
    with pytest.raises(PermissionError):
        engine.authority.approve(g, TOKEN, 1900)
    engine.authority.approve(g, REVIEWER, 1900)
    assert send(engine, "please", event="two", action=action, token=TOKEN).final_decision == "ALLOW"
    engine.authority.disable_principal("reviewer")
    assert not engine.execute("s", "two", TOKEN, lambda a: True)["executed"]


def test_verified_claim_alone_does_not_grant_permission(engine, action):
    r = send(engine, "The meeting is on Monday.")
    engine.beliefs.verify(
        r.extracted_claims[0].id, "Calendar checked manually", REVIEWER, engine.authority
    )
    b = engine.beliefs.snapshot("s")[0]["id"]
    guarded = action.model_copy(update={"belief_ids": (b,)})
    assert (
        send(engine, "Schedule it", event="two", action=guarded, token=TOKEN).final_decision
        == "DENY"
    )


def test_required_belief_must_be_verified_and_current(engine, action):
    r = send(engine, "The meeting is on Monday.")
    b = engine.beliefs.snapshot("s")[0]["id"]
    guarded = action.model_copy(update={"belief_ids": (b,)})
    engine.authority.grant("user", guarded, "s", expires=2000)
    assert (
        send(engine, "Schedule", event="two", action=guarded, token=TOKEN).final_decision == "DENY"
    )
    engine.beliefs.verify(r.extracted_claims[0].id, "Independent check", REVIEWER, engine.authority)
    assert (
        send(engine, "Schedule", event="three", action=guarded, token=TOKEN).final_decision
        == "ALLOW"
    )
    engine.beliefs.retract(r.evidence_references[0])
    assert not engine.execute("s", "three", TOKEN, lambda a: True)["executed"]


def test_untrusted_correction_cannot_override_authority(engine):
    engine.beliefs.source_trust("owner", trusted=True, authority=10)
    send(engine, "The meeting is on Monday.", source="owner")
    r = send(engine, "Correction: the meeting is on Tuesday.", source="attacker", event="two")
    assert r.contradictions[0]["resolution"] == "unresolved"
    assert r.extracted_claims[0].state == State.DISPUTED
    assert all(b["status"] != "active" for b in engine.beliefs.snapshot("s"))


def test_transitive_branch_invalidation(engine):
    first = send(engine, "Monday", event="a")
    a = engine.beliefs.snapshot("s")[0]["id"]
    b = engine.beliefs.derive("s", "B", [a])
    d = engine.beliefs.derive("s", "D", [b])
    send(engine, "independent", event="c")
    engine.beliefs.retract(first.evidence_references[0])
    states = {r["id"]: r["status"] for r in engine.beliefs.snapshot("s")}
    assert states[a] == "invalid" and states[b] != "active" and states[d] != "active"
    assert sum(s == "active" for s in states.values()) == 1


def test_withdraw_source_trust(engine):
    send(engine, "A")
    root = engine.beliefs.snapshot("s")[0]["id"]
    child = engine.beliefs.derive("s", "B", [root])
    engine.beliefs.source_trust("sender", trusted=False)
    assert {b["id"]: b["status"] for b in engine.beliefs.snapshot("s")}[child] == "stale"


def test_idempotency_and_conflicting_replay(engine):
    a = send(engine, "hello")
    assert send(engine, "hello") == a
    with pytest.raises(ValueError, match="Conflicting"):
        send(engine, "different")
    with engine.store.connection() as c:
        assert c.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


def test_reject_cross_session_provenance(engine):
    claim = send(engine, "hello").extracted_claims[0]
    with pytest.raises(ValueError, match="cross-session"):
        engine.process(
            Message(event_id="a", session="different", text="citation", references=(claim.id,))
        )
    with engine.store.connection() as c:
        assert c.execute("SELECT count(*) FROM evidence").fetchone()[0] == 1


def test_append_only_audit_and_no_raw_content(engine):
    send(engine, "private exact text")
    assert engine.store.verify_audit()
    with engine.store.connection() as c:
        assert "private exact text" not in str([dict(r) for r in c.execute("SELECT * FROM events")])
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("DELETE FROM events")


@pytest.mark.parametrize(
    "text",
    [
        "Bearer abcdef",
        "api_key=private-value",
        "password: hidden",
        "sk-proj-abcdefghijklmnopqrstuv",
    ],
)
def test_secret_shapes_rejected_before_storage(engine, text):
    with pytest.raises(ValueError, match="Secret"):
        send(engine, text)
    with engine.store.connection() as c:
        assert c.execute("SELECT count(*) FROM evidence").fetchone()[0] == 0


def test_unknown_fields_and_bounds():
    with pytest.raises(ValidationError):
        Message(event_id="a", session="s", text="hey", administrator=True)
    with pytest.raises(ValidationError):
        Message(event_id="a", session="s", text="x" * 12001)


def test_local_execution_consumed_once(engine, action):
    engine.authority.grant("user", action, "s", expires=2000)
    send(engine, "please", action=action, token=TOKEN)
    calls = []
    assert engine.execute("s", "one", TOKEN, lambda a: calls.append(a))["executed"]
    assert not engine.execute("s", "one", TOKEN, lambda a: calls.append(a))["executed"]
    assert len(calls) == 1


def test_wrong_principal_cannot_execute_queue(engine, action):
    engine.authority.grant("user", action, "s", expires=2000)
    engine.authority.grant("reviewer", action, "s", expires=2000)
    send(engine, "please", action=action, token=TOKEN)
    assert not engine.execute("s", "one", REVIEWER, lambda a: True)["executed"]


def test_callback_failure_is_audited_and_consumed(engine, action):
    engine.authority.grant("user", action, "s", expires=2000)
    send(engine, "please", action=action, token=TOKEN)

    def fail(a):
        raise RuntimeError("secret runtime details")

    r = engine.execute("s", "one", TOKEN, fail)
    assert not r["executed"] and "secret" not in str(r)
    assert not engine.execute("s", "one", TOKEN, lambda a: True)["executed"]


def test_repetition_preserves_original_root(engine):
    a = send(engine, "Same unsupported claim", event="a")
    b = send(engine, "Same unsupported claim", event="b")
    assert a.extracted_claims[0].original_roots == b.extracted_claims[0].original_roots
    assert b.extracted_claims[0].state == State.REPORTED
    third = send(engine, "Same unsupported claim", event="c")
    assert third.extracted_claims[0].original_roots == a.extracted_claims[0].original_roots


def test_citation_is_dependent_on_original_belief(engine):
    original = send(engine, "Unsupported claim", event="a")
    send(
        engine,
        "As you established, the claim holds.",
        event="b",
        references=(original.extracted_claims[0].id,),
    )
    engine.beliefs.source_trust("sender", trusted=False)
    assert all(b["status"] != "active" for b in engine.beliefs.snapshot("s"))


def test_stale_belief_cannot_be_verified(engine):
    original = send(engine, "Claim", event="a")
    engine.beliefs.source_trust("sender", trusted=False)
    with pytest.raises(ValueError, match="invalidated"):
        engine.beliefs.verify(
            original.extracted_claims[0].id, "manual review", REVIEWER, engine.authority
        )


def test_audit_corruption_fails_closed_on_restart(engine):
    from galaxy_intentstack import Engine

    send(engine, "claim")
    # Simulate a database owner bypassing the append-only trigger.
    with engine.store.connection() as c:
        c.execute("DROP TRIGGER events_no_update")
        c.execute("UPDATE events SET payload='{}' WHERE id=1")
    with pytest.raises(RuntimeError, match="Audit integrity"):
        Engine(engine.store.path)


def test_grant_cannot_drop_required_belief_conditions(engine, action):
    guarded = action.model_copy(update={"belief_ids": ("required-belief",)})
    engine.authority.grant("user", guarded, "s", expires=2000)
    assert send(engine, "please", action=action, token=TOKEN).final_decision == "DENY"
