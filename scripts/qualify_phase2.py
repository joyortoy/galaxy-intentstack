"""Run real integration qualification and save raw evidence. Linux, joymux and bwrap required."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path


def run(args, path, *, env=None):
    result = subprocess.run(args, check=False, capture_output=True, text=True, env=env)
    path.write_text(result.stdout + result.stderr)
    if result.returncode:
        raise SystemExit(f"FAILED: {path}; exit={result.returncode}")
    return result.stdout


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", default="reports/phase2")
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
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    probe = root / "work" / ("phase2-qualification-" + uuid.uuid4().hex)
    probe.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = dict(os.environ)
    env["GALAXY_PHASE2_DEMO_REPORT"] = str(output / "integration-demo.json")
    run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "pythonpath=",
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
    print("Qualification evidence saved: " + str(output))
    print("Physical attestation and production qualification remain NOT ESTABLISHED.")


if __name__ == "__main__":
    main()
