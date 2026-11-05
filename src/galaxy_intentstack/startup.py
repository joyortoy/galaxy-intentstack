"""Fail-closed isolated host composition. Existing JoyCtl remains the execution authority."""

import secrets
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from joyctl.hosted import AuthorizationError, HostedControlPlane
from joyctl.runtime.completion import MissionTerminalState
from joyevidence import Ledger

from .revocation import DependencyAuthority, controller_reference


class StartupDenied(AuthorizationError):
    pass


class GuardedControlPlane(HostedControlPlane):
    """Use this host from construction, then activate before worker claims or recovery.

    Scope: local-development SQLite composition. No production/OIDC/attestation claim.
    Health failures latch closed; restore health in a fresh host, never auto-reopen.
    """

    def __init__(self, database, config, *, runtime_database=None):
        if config.mode != "local-development":
            raise StartupDenied("Guarded host is qualified only for isolated local development")
        self._startup_condition = threading.Condition(threading.RLock())
        self._startup_state = "CLOSED"
        self._startup_failure_type = None
        self._startup_integration = None
        self._startup_guard = None
        self._startup_delegate = None
        self._startup_enrollment = None
        self._startup_ledger = None
        self._startup_ledger_paths = None
        self._startup_drain = None
        self._startup_active = 0
        self._native_accepting_requested = False
        super().__init__(database, config, runtime_database=runtime_database)
        super().begin_drain()

    @property
    def _accepting_work(self):
        # Existing upstream readiness reporting also observes the fail-closed health gate.
        if not hasattr(self, "_startup_condition"):
            return False
        with self._startup_condition:
            return self._ready_now()

    @_accepting_work.setter
    def _accepting_work(self, value):
        # A readiness flag alone must never bootstrap a host.
        self._native_accepting_requested = bool(value)

    def _health(self):
        integration, guard = self._startup_integration, self._startup_guard
        if (
            self.config.mode != "local-development"
            or integration is None
            or not isinstance(guard, DependencyAuthority)
            or integration.controller.plane is not self
            or integration.dependency_authority is not guard
            or integration.revocations.guard is not guard
            or guard.delegate is not self._startup_delegate
            or self.snapshot_grant_authority is not guard
            or self.snapshot_verifications.grant_authority is not guard
            or guard.reference != controller_reference(self)
            or self.verification_drain is not self._startup_drain
        ):
            raise ValueError("Expected dependency composition is absent or replaced")
        if self._startup_drain is not None and (
            not self._startup_drain.accepting or self._startup_drain.last_error is not None
        ):
            raise ValueError("Expected native verification drain is not healthy")
        producer = Path(integration.engine.store.path).resolve()
        if any(
            Path(path).resolve() != producer
            for path in (
                guard.store_path,
                integration.delivery.store.path,
                integration.revocations.store.path,
            )
        ):
            raise ValueError("Producer storage identity changed")
        with guard.read_store() as c:
            guard.verify_source(c)
            row = c.execute(
                "SELECT source,user_id,actor_id FROM delivery_meta WHERE singleton=1"
            ).fetchone()
            if not row or tuple(row) != self._startup_enrollment:
                raise ValueError("Producer enrollment changed")
        # Verify pending/acknowledged forwarding metadata without native grant issuance.
        integration.revocations.status()
        ledger = integration.delivery.ledger
        if (
            not isinstance(ledger, Ledger)
            or ledger is not self._startup_ledger
            or (ledger.path.resolve(), ledger.key_path.resolve()) != self._startup_ledger_paths
            or not ledger.path.is_file()
            or not ledger.key_path.is_file()
            or not secrets.compare_digest(ledger.key_path.read_bytes(), ledger.key)
        ):
            raise ValueError("Original authenticated audit ledger/key enrollment unavailable")
        if ledger.verify().get("status") != "verified":
            raise ValueError("Authenticated audit verification unavailable")

    def _fail(self, exc):
        self._startup_state = "FAILED"
        self._native_accepting_requested = False
        self._startup_failure_type = type(exc).__name__

    def _ready_now(self):
        if self._startup_state != "READY" or not self._native_accepting_requested:
            return False
        try:
            self._health()
        except Exception as exc:  # noqa: BLE001 -- runtime dependency faults latch admission closed
            self._fail(exc)
            return False
        return True

    def activate(self, integration):
        with self._startup_condition:
            if self._startup_state == "READY" and integration is self._startup_integration:
                if not self._ready_now():
                    raise StartupDenied("Guarded host health failed; fresh bootstrap required")
                return self.startup_status()
            if self._startup_state != "CLOSED":
                raise StartupDenied("Host cannot be automatically reopened")
            self._startup_state = "STARTING"
            self._startup_integration = integration
            self._startup_active += 1
        try:
            from .controller import Integration

            if not isinstance(integration, Integration):
                raise TypeError("A real integration composition is required")
            self._startup_guard = integration.dependency_authority
            self._startup_delegate = self._startup_guard.delegate
            guard = self._startup_guard
            self._startup_ledger = integration.delivery.ledger
            self._startup_ledger_paths = (
                self._startup_ledger.path.resolve(),
                self._startup_ledger.key_path.resolve(),
            )
            with guard.read_store() as c:
                guard.verify_source(c)
                row = c.execute(
                    "SELECT source,user_id,actor_id FROM delivery_meta WHERE singleton=1"
                ).fetchone()
                self._startup_enrollment = tuple(row) if row else None
                if not row or row["user_id"] != integration.controller.plan.user_id:
                    raise ValueError("Audit enrollment is not bound to the configured principal")
            self._health()
            forwarding = integration.revocations.flush()
            if forwarding["pending"] or forwarding["errors"]:
                raise ValueError("Native revocation recovery is pending or unavailable")
            integration.delivery.require_current()
            self._health()
            with self._startup_condition:
                if self._startup_state != "STARTING":
                    raise StartupDenied("Startup was interrupted by a drain or health failure")
                self._native_accepting_requested = True
                self._startup_state = "READY"
        except Exception as exc:
            with self._startup_condition:
                self._fail(exc)
            raise StartupDenied(
                "Guarded startup failed; review health and use a fresh host"
            ) from exc
        finally:
            with self._startup_condition:
                self._startup_active -= 1
                self._startup_condition.notify_all()
        return self.startup_status()

    def startup_status(self):
        with self._startup_condition:
            ready = self._ready_now()
            return {
                "ready": ready,
                "state": self._startup_state,
                "failure_type": self._startup_failure_type,
                "active_calls": self._startup_active,
                "production_qualified": False,
            }

    def _admit(self):
        with self._startup_condition:
            if not self._ready_now():
                raise StartupDenied("Worker admission or verification is not ready")
            self._startup_active += 1

    def _release(self):
        with self._startup_condition:
            self._startup_active -= 1
            self._startup_condition.notify_all()

    @contextmanager
    def _work(self):
        self._admit()
        try:
            yield
        finally:
            self._release()

    def queue_execution(self, *args, **kwargs):
        with self._work():
            return super().queue_execution(*args, **kwargs)

    def claim_job(self, principal, *, lease_seconds=90):
        with self._work():
            return super().claim_job(principal, lease_seconds=lease_seconds)

    def renew_lease(self, principal, *, lease_id, lease_token, lease_seconds=90):
        # A healthy graceful drain may maintain existing leases; native code still
        # validates the principal, token and expiry. No new lease is issued here.
        with self._startup_condition:
            if self._startup_state == "DRAINING":
                try:
                    self._health()
                except Exception as exc:
                    self._fail(exc)
                    raise StartupDenied("Existing lease health failed") from exc
                self._startup_active += 1
            else:
                self._admit()
        try:
            return super().renew_lease(
                principal, lease_id=lease_id, lease_token=lease_token, lease_seconds=lease_seconds
            )
        finally:
            self._release()

    def resume_pending_snapshot_verifications(self, *, limit=10):
        with self._work():
            return super().resume_pending_snapshot_verifications(limit=limit)

    def _authoritative_complete_from_events(self, **target):
        # Worker custody facts are already committed by the owner. Do not lose them or
        # fabricate completion while the verification startup boundary is closed.
        try:
            self._admit()
        except StartupDenied:
            return {
                "attempt_id": f"attempt_{target['execution_id']}_{target['attempt_number']}",
                "terminal_state": MissionTerminalState.IN_PROGRESS.value,
                "reason": "galaxy_startup_not_ready",
                "authoritative": False,
                "mission_state": "awaiting_joycli_completion",
                "job_state": "result_received",
                "verified": False,
            }
        try:
            return super()._authoritative_complete_from_events(**target)
        finally:
            self._release()

    def start_verification_drain(self, *, interval=1.0, batch_size=10):
        from joyctl.runtime.hosted_verification_drain import HostedVerificationDrain

        with self._work(), self._startup_condition:
            if self._startup_drain is not None:
                raise StartupDenied("A native verification drain is already registered")
            drain = HostedVerificationDrain(self, interval=interval, batch_size=batch_size)
            self._startup_drain = drain
            try:
                drain.start()
            except Exception as exc:
                self._fail(exc)
                raise
            self.verification_drain_required = True
            return drain

    def begin_drain(self):
        with self._startup_condition:
            if self._startup_state in {"READY", "STARTING", "DRAINING"}:
                self._startup_state = "DRAINING"
            self._native_accepting_requested = False
        super().begin_drain()

    def close(self, *, timeout=5.0):
        if not 0 <= timeout <= 30:
            raise ValueError("Shutdown timeout must be between 0 and 30 seconds")
        self.begin_drain()
        deadline = time.monotonic() + timeout
        with self._startup_condition:
            while self._startup_active:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise StartupDenied("In-flight work remains; resources were left open")
                self._startup_condition.wait(remaining)
            self._startup_state = "STOPPING"
        super().close()
        with self._startup_condition:
            self._startup_state = "STOPPED"
