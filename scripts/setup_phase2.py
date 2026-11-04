"""Install local upstream packages into an isolated environment; never copy their source."""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--venv", default=".venv-phase2")
    p.add_argument("--intentstack", default="/home/sam/intentstack-production/current/IntentStack")
    p.add_argument("--joyevidence", default="/home/sam/intentstack-production/current/JoyEvidence")
    p.add_argument("--joyctl", default="/home/sam/joyctl")
    args = p.parse_args()
    if sys.version_info < (3, 12):
        p.error("JoyCtl integration requires Python 3.12+; core remains Python 3.11+")
    root = Path(__file__).resolve().parents[1]
    for name in ("intentstack", "joyevidence", "joyctl"):
        if not (Path(getattr(args, name)) / "pyproject.toml").is_file():
            p.error("Accessible local upstream checkout required: " + name)
    destination = Path(args.venv).resolve()
    subprocess.run([sys.executable, "-m", "venv", str(destination)], check=True)
    python = str(destination / "bin" / "python")
    subprocess.run(
        [python, "-m", "pip", "install", "-r", str(root / "requirements-phase2.lock")], check=True
    )
    subprocess.run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--no-deps",
            args.joyevidence,
            args.intentstack,
            args.joyctl,
            str(root),
        ],
        check=True,
    )
    print("Installed isolated packages; no production services or configurations were changed.")


if __name__ == "__main__":
    main()
