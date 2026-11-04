# Reproduce Phase 2 on host joy

All development and test work stays on host joy. No production service is started or restarted.
Tests create their own HTTP service, Unix JoyMux daemon, keys, controller and memory databases,
then stop only those test-owned processes.

## Clean installation

```sh
ssh joy
cd /home/sam/galaxy-intentstack-dev-20261105
python3 scripts/setup_phase2.py --venv .venv-phase2
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/phase2/clean
```

setup_phase2.py accepts --intentstack, --joyevidence and --joyctl for different accessible local
checkouts. It installs pinned third-party dependencies and the real local upstream packages,
without vendoring their source. Upstream installed-source hashes are in
reports/phase2/upstream-manifest.json. No OpenAI or other model API key is needed.

The qualification runner requires actual Linux bwrap and JoyMux. Missing infrastructure is a
BLOCKED error, not an integration test silently replaced by a mock. It clears pytest's source-path
override, exercising the installed Galaxy package. Retained fixture databases live under a fresh
work/phase2-qualification-* directory; the runner never reuses a previous run's directory.

## Direct checks

```sh
.venv-phase2/bin/python -m pytest -q -o pythonpath= tests/unit tests/adversarial tests/integration
.venv-phase2/bin/python -m pytest -q -o pythonpath= tests/phase2
.venv-phase2/bin/python benchmarks/run.py --rounds 10
.venv-phase2/bin/python benchmarks/detector_quality.py --split development
.venv-phase2/bin/python benchmarks/detector_quality.py --split heldout
.venv-phase2/bin/python benchmarks/detector_quality.py --split challenge
```

Tests assert all 16 requested integration scenarios. Process recovery probes use fresh spawned
interpreters that terminate with os._exit at explicit commit boundaries. Security decisions,
native grant validation, HMAC authentication, custody and sandbox execution use actual upstream
implementations. The only simulated worker infrastructure supplies factual claims, which are
not treated as independent execution verification.

## Independent audit verification

The integration-demo.json report includes audit_ledger_path and audit_key_path. The key remains
in a private test file on host joy and is never printed or committed. Invoke the installed
**joy-evidence console command**, not python -m joyevidence.cli (the upstream module has no
module-entry invocation):

```sh
.venv-phase2/bin/python - <<'PY'
import json
import subprocess
from pathlib import Path
report = json.loads(Path("reports/phase2/clean/integration-demo.json").read_text())
subprocess.run([
    ".venv-phase2/bin/joy-evidence", "verify",
    "--ledger", report["audit_ledger_path"],
    "--key", report["audit_key_path"],
], check=True)
PY
```

Expected status is verified with a nonzero record count. The runner validates that JSON result;
an empty response is not accepted. Verification is a separate process using an isolated test
enrollment key, not an independent production witness or remote acknowledgment.

Authenticated record details bind a local sequence, prior local event commitment and payload
commitment. Ledger HMAC/checkpoint verification protects stored order and tampering. No causal
order between independent services is inferred from timestamps.

## Detector evaluation discipline

Development and held-out fixtures were committed before changing the detector. The held-out
split is separate but author-written and template-heavy; it is not independently annotated.
An additional paraphrase challenge was evaluated, exposed severe misses, and became diagnostic
development evidence. Its later score is explicitly post-feedback, not an untouched holdout.
Before/after files are retained; a remaining selective-evidence paraphrase miss is not hidden.

No classifier result can alter a grant, enroll a principal or bypass policy. The detector is
not qualified for broad user-facing judgments about people's intentions.
