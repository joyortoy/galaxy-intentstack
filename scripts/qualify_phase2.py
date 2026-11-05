"""Run real integration qualification and save raw evidence. Linux, joymux and bwrap required."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


def run(args, path, *, env=None):
    print(f"Running {path.name}...", flush=True)
    started = time.perf_counter()
    result = subprocess.run(args, check=False, capture_output=True, text=True, env=env)
    print(f"{path.name}: {time.perf_counter() - started:.2f}s", flush=True)
    path.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit(f"FAILED: {path}; exit={result.returncode}")
    return result.stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", help="Evidence directory (defaults depend on mode)")
    p.add_argument(
        "--quick",
        action="store_true",
        help="Run the full test suite in temporary storage for routine feedback; "
        "does not qualify durable disk persistence",
    )
    args = p.parse_args()
    if sys.platform != "linux" or not shutil.which("joymux") or not shutil.which("bwrap"):
        p.error("BLOCKED: real isolated Unix JoyMux placement and Linux bwrap are required")
    import intentstack  # noqa: F401 -- required, never silently skip integration dependencies
    import joyctl  # noqa: F401
    import joyevidence  # noqa: F401
    from joyctl.joylang_kernel import JoyLangKernel

    if not shutil.which("node") or not JoyLangKernel().available():
        p.error("BLOCKED: an existing built JoyLang kernel and Node are required; no fallback")
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    output = Path(
        args.output or ("reports/quick-check" if args.quick else "reports/phase2")
    ).resolve()
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if args.quick:
        # Keep fixtures available for independent audit verification and inspection.
        # mkdtemp creates a private directory; no existing user path is cleared.
        probe = Path(tempfile.mkdtemp(prefix="galaxy-quick-")) / "tests"
        print(
            "QUICK CHECK: temporary storage; durable disk qualification NOT ESTABLISHED.",
            flush=True,
        )
    else:
        probe = root / "work" / ("phase2-qualification-" + uuid.uuid4().hex)
        probe.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        print("FULL QUALIFICATION: persistent checkout storage.", flush=True)
    env = dict(os.environ)
    env["GALAXY_PHASE2_DEMO_REPORT"] = str(output / "integration-demo.json")
    env["GALAXY_REVOCATION_DEMO_REPORT"] = str(output / "revocation-demo.json")
    env["GALAXY_STARTUP_DEMO_REPORT"] = str(output / "startup-demo.json")
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "pythonpath=",
            "--durations=10",
            "--basetemp",
            str(probe),
            "--junitxml",
            str(output / "tests.xml"),
        ],
        output / "tests.txt",
        env=env,
    )
    run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src",
            "tests",
            "benchmarks",
            "examples",
            "scripts",
        ],
        output / "lint.txt",
    )
    run(
        [
            sys.executable,
            "-m",
            "ruff",
            "format",
            "--check",
            "src",
            "tests",
            "benchmarks",
            "examples",
            "scripts",
        ],
        output / "format.txt",
    )
    run([sys.executable, "benchmarks/run.py", "--rounds", "10"], output / "benchmark-after.json")
    for split in ("development", "heldout", "challenge"):
        run(
            [sys.executable, "benchmarks/detector_quality.py", "--split", split],
            output / ("detector-" + split + "-after.json"),
        )
    demo = json.loads((output / "integration-demo.json").read_text())
    verification = run(
        [
            str(Path(sys.executable).with_name("joy-evidence")),
            "verify",
            "--ledger",
            demo["audit_ledger_path"],
            "--key",
            demo["audit_key_path"],
        ],
        output / "independent-audit-verification.txt",
    )
    if json.loads(verification).get("status") != "verified":
        raise SystemExit("FAILED: authenticated audit verification did not return verified")
    revoked = json.loads((output / "revocation-demo.json").read_text())
    if (
        not revoked.get("native_revoked")
        or revoked["worker_attempts"] != 0
        or revoked["pending_before_forwarding"] != 1
        or revoked["revocation"]["native_acknowledged"] != 1
    ):
        raise SystemExit(
            "FAILED: dependency revocation demonstration did not establish the required boundary"
        )
    revoked_verification = run(
        [
            str(Path(sys.executable).with_name("joy-evidence")),
            "verify",
            "--ledger",
            revoked["audit_ledger_path"],
            "--key",
            revoked["audit_key_path"],
        ],
        output / "independent-revocation-audit-verification.txt",
    )
    if json.loads(revoked_verification).get("status") != "verified":
        raise SystemExit("FAILED: revocation audit did not independently verify")
    startup = json.loads((output / "startup-demo.json").read_text())
    if (
        not startup["startup"]["ready"]
        or not startup["native_passed"]
        or startup["production_qualified"]
        or startup["observation"]["semantic_acceptance"]
        or startup["physical_attestation"] != "NOT_ESTABLISHED"
    ):
        raise SystemExit("FAILED: guarded startup demonstration failed")
    checked = run(
        [
            str(Path(sys.executable).with_name("joy-evidence")),
            "verify",
            "--ledger",
            startup["audit_ledger_path"],
            "--key",
            startup["audit_key_path"],
        ],
        output / "independent-startup-audit-verification.txt",
    )
    if json.loads(checked).get("status") != "verified":
        raise SystemExit("FAILED: startup audit did not independently verify")
    summary = {
        "mode": "quick" if args.quick else "full",
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "fixture_path": str(probe),
        "durable_disk_qualification_run": not args.quick,
        "production_qualified": False,
    }
    (output / "run-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(("Quick-check" if args.quick else "Qualification") + " evidence saved: " + str(output))
    print(f"Total: {summary['elapsed_seconds']:.2f}s", flush=True)
    print("Physical attestation and production qualification remain NOT ESTABLISHED.")


if __name__ == "__main__":
    main()
