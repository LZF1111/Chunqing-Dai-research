"""Run one hypothesis across several seeds and write an aggregate result."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Any


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.json"))
    parser.add_argument("--program", type=Path, default=Path("program.md"))
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--results-file", type=Path, default=Path("results/experiments.jsonl"))
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--hypothesis", required=True)
    parser.add_argument("--seeds", default="42,43,44")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--total-timeout-seconds", type=int, default=28800)
    return parser


def _aggregate(values: list[Any], key: str = "") -> Any:
    if not values:
        return None
    if all(isinstance(value, dict) for value in values):
        keys = sorted({child_key for value in values for child_key in value})
        return {
            child_key: _aggregate(
                [value[child_key] for value in values if child_key in value],
                child_key,
            )
            for child_key in keys
        }
    if all(isinstance(value, (int, float)) for value in values):
        if key == "sample_count":
            return values[0]
        return float(mean(values))
    if all(value is None for value in values):
        return None
    return values[0]


def main() -> None:
    args = _parser().parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if len(seeds) < 3:
        raise ValueError("A seed sweep needs at least three seeds")
    if len(set(seeds)) != len(seeds):
        raise ValueError("Seed values must be unique")

    root = Path(__file__).resolve().parents[1]
    run_script = root / "run_experiment.py"
    summary_dir = args.artifact_root / f"{args.experiment_id}-seed-summary"
    summary_path = summary_dir / "seed_summary.json"
    if summary_dir.exists() and any(summary_dir.iterdir()):
        raise FileExistsError(f"Seed summary directory already exists: {summary_dir}")
    summary_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    successful_runs: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    metric_payloads: list[dict[str, Any]] = []
    for seed in seeds:
        remaining = args.total_timeout_seconds - (time.monotonic() - started)
        if remaining <= 0:
            failures.append({"seed": seed, "status": "total_timeout"})
            break
        experiment_id = f"{args.experiment_id}-seed-{seed}"
        command = [
            sys.executable,
            str(run_script),
            "--model",
            args.model,
            "--data-dir",
            str(args.data_dir),
            "--manifest",
            str(args.manifest),
            "--program",
            str(args.program),
            "--artifact-root",
            str(args.artifact_root),
            "--results-file",
            str(args.results_file),
            "--experiment-id",
            experiment_id,
            "--seed",
            str(seed),
            "--hypothesis",
            args.hypothesis,
            "--timeout-seconds",
            str(min(args.timeout_seconds, max(1, int(remaining)))),
        ]
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        artifact_dir = args.artifact_root / experiment_id
        metrics_path = artifact_dir / "validation_metrics.json"
        if completed.returncode != 0 or not metrics_path.exists():
            failures.append(
                {
                    "seed": seed,
                    "experiment_id": experiment_id,
                    "status": "failed",
                    "return_code": completed.returncode,
                    "stdout_tail": completed.stdout[-2000:],
                    "stderr_tail": completed.stderr[-2000:],
                }
            )
            continue
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        metric_payloads.append(payload["metrics"])
        successful_runs.append(
            {
                "seed": seed,
                "experiment_id": experiment_id,
                "artifact_dir": str(artifact_dir),
                "metrics_path": str(metrics_path),
            }
        )

    summary = {
        "summary_schema": "p0-seed-summary-v1",
        "experiment_id": args.experiment_id,
        "model": args.model,
        "hypothesis": args.hypothesis,
        "seeds": seeds,
        "seed_count": len(successful_runs),
        "successful_runs": successful_runs,
        "failures": failures,
        "status": "success" if len(successful_runs) == len(seeds) else "failed",
        "metrics": _aggregate(metric_payloads),
        "duration_seconds": round(time.monotonic() - started, 3),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "success":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
