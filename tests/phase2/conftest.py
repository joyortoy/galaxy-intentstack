"""Real local upstream services. All databases/keys are temporary test enrollment."""

import multiprocessing
import secrets
import socket
import subprocess
import time
from dataclasses import asdict
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

pytest.importorskip("intentstack")
pytest.importorskip("joyctl")
pytest.importorskip("joyevidence")

import httpx
import uvicorn
from intentstack.api import create_app
from intentstack.auth import Principal, TokenRegistry
from intentstack.data_agent import DataAgent
from joyctl.hosted import AgentSession, HostedConfig, HostedControlPlane
from joyctl.joylang import SourceMessage, compile_joylang
from joyctl.joylang_kernel import JoyLangKernel
from joyctl.policy import (
    NetworkPolicy,
    PolicyConfig,
    evaluate_policy,
    propose_action,
    scope_strategy,
)
from joyctl.runtime.intake.service import MissionIntakeRequest
from joyctl.verification_receipts import source_fingerprint
from joyevidence import Ledger

from galaxy_intentstack import Action, Engine
from galaxy_intentstack.controller import Integration, JoyCtlController, Plan
from galaxy_intentstack.delivery import AuditDelivery
from galaxy_intentstack.retrieval import IntentStackRetrieval


class TestEnvironment(SimpleNamespace):
    def __repr__(self):
        return "<Isolated qualification environment; credentials omitted>"


def serve(path, token, listener):
    caps = frozenset(
        {
            "memory:read:deep",
            "memory:write:deep",
            "evidence:read",
            "evidence:verify",
            "memory:confirm",
        }
    )
    app = create_app(
        path, TokenRegistry({token: Principal("source-author", "retrieval-user", caps)})
    )
    config = uvicorn.Config(app, log_level="critical", access_log=False)
    uvicorn.Server(config).run(sockets=[listener])


@pytest.fixture
def retrieval_service(tmp_path):
    token = secrets.token_urlsafe(32)
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}"
    proc = multiprocessing.get_context("spawn").Process(
        target=serve, args=(tmp_path / "upstream.db", token, listener), daemon=True
    )
    proc.start()
    client = httpx.Client(base_url=url, headers={"Authorization": "Bearer " + token}, timeout=5)
    try:
        for _ in range(100):
            try:
                if client.get("/health").status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.02)
        else:
            raise RuntimeError("Isolated IntentStack service did not start")
        agent = DataAgent(url, token)
        yield TestEnvironment(
            client=client,
            agent=agent,
            path=tmp_path / "upstream.db",
            token=token,
            url=url,
            proc=proc,
        )
        agent.close()
    finally:
        client.close()
        proc.terminate()
        proc.join(5)
        listener.close()


@pytest.fixture
def integrated(tmp_path, request):
    config = HostedConfig(secret_key=secrets.token_urlsafe(48))
    plane = HostedControlPlane.sqlite(tmp_path / "controller.db", config=config)
    user = plane.create_user("isolated@example.invalid", "Isolated test owner")
    org = plane.create_organisation(user["id"], "Isolated Galaxy")
    principal = plane.principal(user["id"], org["id"])
    pairing = plane.create_pairing(principal)
    paired = plane.claim_pairing(
        pairing["pairing_code"],
        device_name="Isolated test transport",
        capabilities=("read_repository", "run_tests", "artifact_upload_bounded_v1"),
    )
    auth = plane.authenticate_device(paired["device_credential"])
    device_token = auth["access_token"]
    session = AgentSession(plane, device_token)
    session.heartbeat(
        {
            "protocol_version": "1",
            "capabilities": ["read_repository", "run_tests", "artifact_upload_bounded_v1"],
        }
    )
    workspace = plane.create_workspace(principal, "Qualification")
    project = plane.create_project(
        principal,
        workspace["id"],
        "Read-only snapshot",
        "isolated-snapshot",
        device_id=paired["device_id"],
    )
    mission = plane.create_mission(
        principal,
        workspace_id=workspace["id"],
        project_id=project["id"],
        title="Inspect isolated evidence",
    )
    intake = plane.mission_control.intake.accept(
        MissionIntakeRequest(
            mission_id=mission["id"],
            objective=mission["title"],
            available_capabilities=frozenset({"read_repository", "run_tests"}),
            idempotency_key="isolated-intake:" + mission["id"],
            origin="galaxy_compiled_plan_qualification",
            compatibility=False,
            approvals_satisfied=True,
            dispatch_compiled_only=True,
            metadata={"organisation_id": org["id"], "project_id": project["id"]},
        )
    )
    assert len(intake.plan.steps) == 1
    step_id = intake.plan.steps[0].step_id
    prompt = plane.prompt_compiler.compile(
        mission_id=mission["id"],
        decision_id=intake.decision.id,
        plan_id=intake.plan.id,
        step_id=step_id,
        joylang_program="@objective\nInspect the controller-registered read-only snapshot and retain evidence.\n@constraints\nDo not change files. Do not use network access.\n@verification\nRetain the independent native verification receipt.\n",
        target_harness="hosted",
        profile="read_only_analysis",
        organisation_id=org["id"],
    )
    root = tmp_path / "source"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "verify.py").write_text("assert sum([2, 3, 4]) == 9\n")
    source = """desired_outcome: Inspect isolated evidence
success_criteria:
  - Verify local arithmetic
hard_constraints:
  - No network
priority_tier: normal
motivation_policy: satisfy_mandatory_before_optional
memory_policy: canonical_memory=IntentStack; external_ingress=IntentDeck
source_trust_policy: external=untrusted_by_default
verification_requirements:
  - Local read-only verification
approval_rules: mode=human_required_for_high_risk
resource_budgets: max_runtime_seconds=30; max_files_changed=0
"""
    compiled = compile_joylang(
        SourceMessage(
            source_message_id="isolated-policy",
            authenticated_actor=principal.user_id,
            channel="local-test",
            content=source,
            received_at=datetime.now(UTC).isoformat(),
        )
    )
    options = request.param if hasattr(request, "param") and isinstance(request.param, dict) else {}
    commands = tuple(options.get("commands", ("/usr/bin/python3 verify.py",)))
    (root / "verify_two.py").write_text("assert 9 * 9 == 81\n")
    kernel = JoyLangKernel()
    if not kernel.available():
        raise RuntimeError("BLOCKED: existing built JoyLang kernel is required; no fallback")
    contract = tmp_path / "readonly-contract.joy"
    contract.write_text(
        "joy 0.2\nid: galaxy-readonly-review\n\nintent\n"
        "  outcome: Verify the isolated snapshot and retain it for review\n\nproof\n"
        + "".join("  test: " + command + "\n" for command in commands)
        + "  human: independent_review_completed\n"
    )
    admitted = kernel.admit_file(contract)
    assert admitted["ok"] is True
    admitted_spec = admitted["spec"]
    test_obligations = {
        p["id"]: p["require"] for p in admitted_spec["proof"] if p["class"] == "test"
    }

    proposal = propose_action(
        compiled_intent=compiled,
        objective_id=mission["id"],
        strategy_revision="isolated-v1",
        action_kind="verify_snapshot",
        requested_paths=(str(root),),
        requested_tools=commands,
        network_policy=NetworkPolicy.DENY,
        resource_limits={"max_runtime_seconds": 30, "max_files_changed": 0},
        agent_or_role=plane.snapshot_verifier_identity,
    )
    strategy = scope_strategy(
        proposal,
        allowed_paths=(str(root),),
        allowed_tools=commands,
        resource_limits={"max_runtime_seconds": 30, "max_files_changed": 0},
    )
    evaluated = evaluate_policy(
        compiled,
        proposal,
        strategy,
        config=PolicyConfig(
            allowed_paths=(str(root),),
            allowed_tools=commands,
            max_resource_limits={"max_runtime_seconds": 30, "max_files_changed": 0},
        ),
    )
    assert evaluated.grant is not None
    native = evaluated.grant
    worker = plane.record_execution_authorization(
        principal,
        mission_id=mission["id"],
        step_id=step_id,
        grant={
            **asdict(native),
            "capabilities": ["read_repository", "run_tests"],
            "production_mutation": False,
        },
    )
    registered = plane.record_snapshot_verification_authorization(
        principal,
        worker_authorization_id=worker["authorization_id"],
        snapshot_root=root,
        source_sha256=source_fingerprint(str(root)),
        commands=commands,
        grant=native,
        admitted_spec=admitted_spec if getattr(request, "param", True) else None,
        test_obligation_commands=test_obligations if getattr(request, "param", True) else {},
        current_intent_revision=compiled.revision,
        current_policy_revision=native.policy_revision,
        timeout_seconds=30,
    )
    plan = Plan(
        organisation_id=org["id"],
        user_id=user["id"],
        device_id=paired["device_id"],
        mission_id=mission["id"],
        step_id=step_id,
        authorization_id=worker["authorization_id"],
        verification_id=registered["verification_authorization_id"],
        workspace_ref="isolated-snapshot",
        prompt_id=prompt.prompt_id,
        expected_prompt_hash=prompt.prompt_hash,
        admitted_plan_id=intake.plan.id,
        admitted_decision_id=intake.decision.id,
        require_physical_attestation=False,
    )
    engine = Engine(tmp_path / "galaxy.db")
    ledger = Ledger(tmp_path / "sink.db", tmp_path / "sink.key")
    delivery = AuditDelivery(
        engine.store, ledger, user_id=principal.user_id, actor_id="galaxy-test"
    )
    controller = JoyCtlController(plane, plan)
    integration = Integration(engine, controller, delivery)
    return TestEnvironment(
        prompt=prompt,
        intake=intake,
        plane=plane,
        config=config,
        principal=principal,
        native=native,
        plan=plan,
        controller=controller,
        integration=integration,
        engine=engine,
        ledger=ledger,
        delivery=delivery,
        human_token=plane.issue_human_access_token(principal),
        device_token=device_token,
        agent=session,
        action=Action(kind="verify_snapshot", resource="isolated-snapshot", scope="read"),
        root=root,
    )


def submit(f, **overrides):
    args = {
        "operation_id": "operation-1",
        "session": "integration-session",
        "action": f.action,
        "human_token": f.human_token,
        "device_token": f.device_token,
    }
    args.update(overrides)
    return f.integration.submit(**args)


def remember(service, text):
    response = service.client.post(
        "/v1/memories", json={"text": text, "scope": "deep", "source_ref": "isolated:conversation"}
    )
    response.raise_for_status()
    return response.json()


def retrieve(f, service, request_id="retrieve-1", **kwargs):
    adapter = IntentStackRetrieval(
        f.engine, service.agent, endpoint_id="isolated-intentstack", user_id="retrieval-user"
    )
    results = adapter.retrieve(
        request_id=request_id, session="integration-session", query="meeting", **kwargs
    )
    return adapter, results


@pytest.fixture
def isolated_joymux(monkeypatch):
    import os
    import tempfile
    from pathlib import Path

    from joyctl.joymux_placement_client import (
        JoyMuxPlacementClientError,
        UnixSocketJoyMuxPlacementClient,
    )

    with tempfile.TemporaryDirectory(prefix="galaxy-mux-") as directory:
        data = Path(directory)
        log = (data / "daemon.log").open("w")
        env = dict(os.environ)
        env["JOYMUX_DATA_DIR"] = str(data)
        env.pop("JOYMUX_SOCKET", None)
        proc = subprocess.Popen(
            ["joymux", "--data-dir", str(data), "serve", "--unix"], env=env, stdout=log, stderr=log
        )
        try:
            path = data / "runtime.sock"
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError(
                        "Isolated JoyMux daemon exited: " + (data / "daemon.log").read_text()
                    )
                if path.exists():
                    try:
                        UnixSocketJoyMuxPlacementClient(path, timeout_ms=500).health()
                        break
                    except JoyMuxPlacementClientError:
                        continue
                time.sleep(0.02)
            else:
                raise RuntimeError(
                    "Isolated Unix JoyMux placement not ready: " + (data / "daemon.log").read_text()
                )
            monkeypatch.setenv("JOYCTL_PLACEMENT_TRANSPORT", "unix_socket")
            monkeypatch.setenv("JOYCTL_JOYMUX_PLACEMENT_SOCKET", str(path))
            yield path
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            log.close()
