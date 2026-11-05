# Routine quick-check measurements

Date: 2026-11-05. Host: joy. Python 3.13.7.

All 169 installed-package tests passed in 16.80 seconds. Total runner time was 17.44 seconds,
including lint, formatting, benchmarks and three independent joy-evidence audit verifications.
No tests or validation stages were removed. The prior persistent-storage test run took 177.50
seconds; quick mode provides roughly ten times faster routine feedback under these conditions.

A controlled two-test comparison measured 0.60 seconds on /tmp versus 3.37 seconds under the
checkout work directory. On joy, /tmp is tmpfs and the checkout is on ext4. SQLite-heavy fixture
creation and writes account for much of the difference. These timings are observations, not a
performance guarantee for other hosts or workloads.

Quick mode retains a private temporary fixture directory and saves a separate report by default.
Its process-exit recovery tests still run, but memory-backed storage does not qualify durable
on-disk persistence or power-loss behavior. Full mode retains the existing checkout work directory
and all validation stages. Existing full qualification and user rerun evidence were preserved.

Every validation stage now prints its start and elapsed time. run-summary.json records the mode,
total elapsed time and fixture location; tests.txt lists the ten slowest test durations.

Run on joy:

```sh
cd /home/sam/galaxy-intentstack-startup-20261105
.venv-phase2/bin/python scripts/qualify_phase2.py --quick
```

For persistent-storage qualification, omit --quick and choose the full report directory:

```sh
.venv-phase2/bin/python scripts/qualify_phase2.py --output reports/startup-guard
```

Production qualification and physical attestation remain unestablished.
