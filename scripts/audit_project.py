"""Check that the repository contains the minimum P0 audit materials."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REQUIRED_FILES = [
    "README.md",
    "GETTING_STARTED.md",
    "AGENT_PROMPT.md",
    "ISSUE_CONTEXT.md",
    "DECISIONS.md",
    "AUDIT_REPORT.md",
    "program.md",
    "data/README.md",
    "data/collocation_metadata.example.json",
    "decisions/0001-freeze-p0-aod-protocol.md",
    "prepare.py",
    "train.py",
    "evaluate.py",
    "gate.py",
    "run_experiment.py",
    "scripts/run_seed_sweep.py",
]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile", action="store_true", help="Compile Python files as part of the audit")
    return parser


def _check_files(root: Path) -> list[dict[str, object]]:
    checks = []
    for relative in REQUIRED_FILES:
        path = root / relative
        checks.append(
            {
                "check": f"required file {relative}",
                "passed": path.is_file(),
            }
        )
    return checks


def _check_text(root: Path, relative: str, phrases: list[str]) -> list[dict[str, object]]:
    text = (root / relative).read_text(encoding="utf-8")
    return [
        {
            "check": f"{relative} contains {phrase!r}",
            "passed": phrase in text,
        }
        for phrase in phrases
    ]


def _compile(root: Path) -> dict[str, object]:
    completed = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "prepare.py", "train.py", "evaluate.py", "gate.py", "run_experiment.py", "src", "scripts"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return {
        "check": "Python compilation",
        "passed": completed.returncode == 0,
        "stdout": completed.stdout[-2000:],
        "stderr": completed.stderr[-2000:],
    }


def main() -> None:
    args = _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    checks = _check_files(root)
    checks.extend(_check_text(root, "program.md", ["manifest", "gate.py", "测试集"]))
    checks.extend(_check_text(root, "AGENT_PROMPT.md", ["experiment_id", "manifest", "gate.py"]))
    if args.compile:
        checks.append(_compile(root))
    passed = all(check["passed"] for check in checks)
    report = {
        "status": "passed" if passed else "failed",
        "checks": checks,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
