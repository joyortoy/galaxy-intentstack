"""Real prompt-store, intake and queue contracts; no legacy instruction fallback."""

import uuid
import warnings
from dataclasses import replace

import pytest

from .conftest import submit


def test_queue_uses_admitted_prompt_without_compatibility_or_deprecation(integrated, monkeypatch):
    f = integrated
    actual = f.plane.queue_execution
    captured = []

    def record(*args, **kwargs):
        captured.append(kwargs)
        return actual(*args, **kwargs)

    monkeypatch.setattr(f.plane, "queue_execution", record)
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        result = submit(f)
    assert result["controller_accepted"], result
    assert captured[0]["prompt_id"] == f.prompt.prompt_id
    assert captured[0]["expected_prompt_hash"] == f.prompt.prompt_hash
    assert "instruction" not in captured[0]
    job = f.plane.get_job(f.principal, result["job_id"])
    assert job["compatibility_mode"] is False
    assert job["constraints"]["plan_id"] == f.intake.plan.id
    assert job["constraints"]["decision_id"] == f.intake.decision.id
    assert "compatibility_origin" not in job["constraints"]
    assert not any(issubclass(item.category, DeprecationWarning) for item in seen)


@pytest.mark.parametrize(
    "field,value",
    [
        ("prompt_id", None),
        ("expected_prompt_hash", None),
        ("admitted_plan_id", None),
        ("admitted_decision_id", None),
        ("prompt_id", "nonexistent-prompt"),
        ("expected_prompt_hash", "0" * 64),
        ("admitted_plan_id", "foreign-plan"),
        ("admitted_decision_id", "foreign-decision"),
    ],
)
def test_missing_or_mismatched_pins_deny_without_fallback(integrated, field, value):
    f = integrated
    before = len(
        f.plane.prompt_store.list_for_mission(
            f.plan.mission_id, organisation_id=f.plan.organisation_id
        )
    )
    f.controller.plan = f.plan.model_copy(update={field: value})
    result = submit(f)
    assert result["decision"] == "DENY", result
    assert (
        len(
            f.plane.prompt_store.list_for_mission(
                f.plan.mission_id, organisation_id=f.plan.organisation_id
            )
        )
        == before
    )
    with f.plane.database.connect() as c:
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"mission_id": "foreign-mission"},
        {"step_id": "foreign-step"},
        {"plan_id": "foreign-plan"},
        {"decision_id": "foreign-decision"},
        {"validation_status": "failed"},
        {"profile": "repository_implementation"},
        {"target_harness": "unrelated-harness"},
    ],
)
def test_stored_prompt_must_match_readonly_admission(integrated, change):
    f = integrated
    prompt = replace(f.prompt, prompt_id="prompt-" + uuid.uuid4().hex, **change)
    f.plane.prompt_store.save(prompt, organisation_id=f.plan.organisation_id)
    f.controller.plan = f.plan.model_copy(update={"prompt_id": prompt.prompt_id})
    result = submit(f)
    assert result["decision"] == "DENY", result


def test_cross_tenant_prompt_is_not_readable_for_dispatch(integrated):
    f = integrated
    prompt = replace(f.prompt, prompt_id="prompt-" + uuid.uuid4().hex)
    f.plane.prompt_store.save(prompt, organisation_id="foreign-tenant")
    f.controller.plan = f.plan.model_copy(update={"prompt_id": prompt.prompt_id})
    assert submit(f)["decision"] == "DENY"


def test_stored_text_tampering_denies_native_dispatch(integrated):
    f = integrated
    with f.plane.runtime_database.connect() as c:
        c.execute(
            "UPDATE compiled_prompts SET text=? WHERE prompt_id=?",
            ("Altered after compilation", f.prompt.prompt_id),
        )
    assert submit(f)["decision"] == "DENY"
    with f.plane.database.connect() as c:
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 0


def test_changing_prompt_pin_cannot_reuse_existing_operation(integrated):
    f = integrated
    first = submit(f)
    assert first["controller_accepted"]
    prompt = replace(f.prompt, prompt_id="prompt-" + uuid.uuid4().hex)
    f.plane.prompt_store.save(prompt, organisation_id=f.plan.organisation_id)
    f.controller.plan = f.plan.model_copy(update={"prompt_id": prompt.prompt_id})
    assert submit(f)["decision"] == "DENY"
    with f.plane.database.connect() as c:
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 1


@pytest.mark.parametrize("integrated", [False], indirect=True)
def test_owner_still_requires_semantic_contract_for_canonical_queue(integrated):
    f = integrated
    result = submit(f)
    assert result["decision"] == "DENY", result
    with f.plane.database.connect() as c:
        assert c.execute("SELECT count(*) FROM execution_jobs").fetchone()[0] == 0
