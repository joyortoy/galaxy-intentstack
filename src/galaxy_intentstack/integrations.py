"""Read-only boundary adapters, no network access or canonical memory writes."""
from .models import Interpretation, Message


def incoming_message(*, text, event_id, session):
    return Message(text=text, event_id=event_id, session=session)


def memory_result(record, *, store_id, session):
    # Match IntentStack revision/source_ref shape. Confirmation is not execution permission.
    required = ("id", "revision", "text", "source_ref")
    if any(k not in record for k in required) or type(record["revision"]) is not int:
        raise ValueError("Memory ID, revision, text and source_ref required")
    if record["revision"] < 1 or not store_id:
        raise ValueError("Invalid memory revision or source store")
    return Message(event_id=f"{store_id}:{record['id']}:{record['revision']}",
                   session=session, text=record["text"], source_type="memory")


def classifier_output(result, evidence_id):
    # A classifier's claimed certainty, roles or permissions are ignored.
    label = result.get("intent")
    if not isinstance(label, str) or not 1 <= len(label) <= 100:
        raise ValueError("Bounded intent label required")
    return Interpretation(description="Classifier suggestion: " + label,
                          evidence_references=(evidence_id,))


def agent_action(request):
    from .models import Action
    return Action.model_validate(request)


def policy_authorization(engine, action, *, session, token):
    with engine.store.connection() as c:
        return engine.authority.check(c, action, session, token)


def audit_events(engine, *, after_id=0, limit=100):
    if not 1 <= limit <= 256 or after_id < 0:
        raise ValueError("Bounded cursor and limit required")
    with engine.store.connection() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM events WHERE id>? ORDER BY id LIMIT ?", (after_id, limit))]
