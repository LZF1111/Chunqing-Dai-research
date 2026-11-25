"""Apply the fixed acceptance rules to one validation result."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data import sha256_file


MIN_IMPROVEMENT = 0.001
MAX_RELATIVE_DEGRADATION = 0.10


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        type=Path,
        required=True,
        help="Path to an evaluate.py validation metrics JSON file",
    )
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument(
        "--best",
        type=Path,
        default=Path("results/best.json"),
        help="Current accepted result",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path for the verdict JSON. Defaults to the candidate directory.",
    )
    parser.add_argument(
        "--initialize",
        action="store_true",
        help="Register the candidate as the first baseline",
    )
    parser.add_argument(
        "--replace-best",
        action="store_true",
        help="Allow explicit replacement of an existing best result during initialization",
    )
    parser.add_argument(
        "--smoke-only",
        action="store_true",
        help="Use synthetic data for a software smoke test and write a smoke best file",
    )
    return parser


def _read_metrics(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Candidate metrics do not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("Candidate metrics JSON must contain an object named 'metrics'")
    return metrics


def _assert_finite(value: Any, path: str = "metrics") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _assert_finite(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_finite(child, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} contains a non-finite value")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _verify_single_artifact(candidate_path: Path, smoke_only: bool) -> dict[str, Any]:
    artifact_dir = candidate_path.parent
    required_files = [
        "record.json",
        "manifest.json",
        "config.json",
        "environment.json",
        "train.stdout.log",
        "train.stderr.log",
        "evaluate.stdout.log",
        "evaluate.stderr.log",
        "verdict.json",
    ]
    missing = [name for name in required_files if not (artifact_dir / name).is_file()]
    if missing:
        raise ValueError(
            "Candidate artifact is incomplete. Missing: " + ", ".join(missing)
        )
    record = json.loads((artifact_dir / "record.json").read_text(encoding="utf-8"))
    if record.get("status") != "success":
        raise ValueError("Candidate artifact record is not a successful experiment")
    for field in ("git_commit", "data_manifest_sha256", "program_sha256", "config_sha256"):
        if not record.get(field):
            raise ValueError(f"Candidate record does not contain {field}")
    manifest = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    dataset_kind = manifest.get("dataset_kind", "unknown")
    if smoke_only:
        if dataset_kind != "synthetic":
            raise ValueError("--smoke-only requires a manifest with dataset_kind=synthetic")
    elif dataset_kind != "real":
        raise ValueError(
            "Scientific gates require dataset_kind=real. Use --smoke-only only for synthetic checks."
        )
    if dataset_kind == "real":
        metadata = manifest.get("collocation_metadata", {})
        required_metadata = [
            "satellite_product",
            "satellite_product_version",
            "aeronet_version",
            "temporal_window_minutes",
            "spatial_window",
            "pixel_aggregation",
            "quality_rule_id",
            "source_files",
        ]
        missing_metadata = [key for key in required_metadata if key not in metadata]
        if missing_metadata:
            raise ValueError(
                "Real-data manifest is missing collocation metadata: "
                + ", ".join(missing_metadata)
            )
    if record.get("data_manifest_sha256") != sha256_file(artifact_dir / "manifest.json"):
        raise ValueError("Candidate record hash does not match the saved manifest copy")
    return {"record": record, "manifest": manifest}


def _verify_artifact(candidate_path: Path, smoke_only: bool) -> dict[str, Any]:
    payload = json.loads(candidate_path.read_text(encoding="utf-8"))
    if payload.get("summary_schema") != "p0-seed-summary-v1":
        return _verify_single_artifact(candidate_path, smoke_only)
    if payload.get("status") != "success" or payload.get("seed_count", 0) < 3:
        raise ValueError("Seed summary must contain at least three successful runs")
    child_results = []
    for run in payload.get("successful_runs", []):
        metrics_path = Path(run["metrics_path"])
        child_results.append(_verify_single_artifact(metrics_path, smoke_only))
    manifests = [result["manifest"] for result in child_results]
    manifest_hashes = {
        result["record"].get("data_manifest_sha256") for result in child_results
    }
    if len(manifest_hashes) != 1:
        raise ValueError("All seed runs must use the same data manifest")
    return {
        "record": {
            "experiment_id": payload["experiment_id"],
            "status": "success",
            "seed_count": payload["seed_count"],
            "data_manifest_sha256": next(iter(manifest_hashes)),
        },
        "manifest": manifests[0],
    }


def _group_degradations(
    candidate: dict[str, Any],
    best: dict[str, Any],
    maximum: float,
) -> list[dict[str, Any]]:
    candidate_bins = candidate.get("by_true_aod_bin", {})
    best_bins = best.get("by_true_aod_bin", {})
    failures = []
    for name, candidate_group in candidate_bins.items():
        best_group = best_bins.get(name, {})
        candidate_rmse = candidate_group.get("rmse")
        best_rmse = best_group.get("rmse")
        if not candidate_group.get("sample_count") or not best_group.get("sample_count"):
            continue
        if candidate_rmse is None or best_rmse in (None, 0):
            continue
        relative_change = (candidate_rmse - best_rmse) / best_rmse
        if relative_change > maximum:
            failures.append(
                {
                    "group": name,
                    "candidate_rmse": candidate_rmse,
                    "best_rmse": best_rmse,
                    "relative_change": relative_change,
                }
            )
    return failures


def main() -> None:
    args = _parser().parse_args()
    if args.smoke_only and args.best == Path("results/best.json"):
        args.best = Path("results/smoke-best.json")
    artifact_info = _verify_artifact(args.candidate, args.smoke_only)
    candidate_record = artifact_info["record"]
    candidate_manifest = artifact_info["manifest"]
    candidate_metrics = _read_metrics(args.candidate)
    _assert_finite(candidate_metrics)
    candidate_rmse = candidate_metrics.get("rmse")
    sample_count = candidate_metrics.get("sample_count", 0)
    if candidate_rmse is None or sample_count <= 0:
        raise ValueError("Candidate must contain a finite RMSE and a positive sample count")

    output = args.output or args.candidate.parent / "verdict.json"
    now = datetime.now(timezone.utc).isoformat()
    if args.initialize:
        if args.best.exists() and not args.replace_best:
            raise FileExistsError(
                f"Best result already exists at {args.best}. Use --replace-best explicitly."
            )
        best_payload = {
            "experiment_id": args.experiment_id,
            "candidate_metrics_path": str(args.candidate),
            "candidate_record": candidate_record,
            "dataset_kind": candidate_manifest.get("dataset_kind", "unknown"),
            "metrics": candidate_metrics,
            "initialized_at_utc": now,
            "verdict": "baseline_initialized",
        }
        _write_json(args.best, best_payload)
        verdict = {
            "experiment_id": args.experiment_id,
            "status": "baseline_initialized",
            "accepted": True,
            "reason": "The first baseline was explicitly initialized by the operator.",
            "candidate_rmse": candidate_rmse,
            "best_path": str(args.best),
            "created_at_utc": now,
        }
        _write_json(output, verdict)
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
        return

    if not args.best.exists():
        raise FileNotFoundError(
            f"No current best result at {args.best}. Initialize a baseline first."
        )
    best_payload = json.loads(args.best.read_text(encoding="utf-8"))
    best_metrics = best_payload.get("metrics", {})
    _assert_finite(best_metrics, "best.metrics")
    best_rmse = best_metrics.get("rmse")
    if best_rmse is None:
        raise ValueError("Current best result does not contain RMSE")

    improvement = best_rmse - candidate_rmse
    group_failures = _group_degradations(
        candidate_metrics,
        best_metrics,
        MAX_RELATIVE_DEGRADATION,
    )
    accepted = improvement >= MIN_IMPROVEMENT and not group_failures
    reasons = []
    if improvement < MIN_IMPROVEMENT:
        reasons.append(
            f"RMSE improvement {improvement:.6f} is below {MIN_IMPROVEMENT:.6f}"
        )
    if group_failures:
        reasons.append("one or more AOD bins exceeded the degradation threshold")

    verdict = {
        "experiment_id": args.experiment_id,
        "status": "accepted" if accepted else "rejected",
        "accepted": accepted,
        "candidate_rmse": candidate_rmse,
        "best_rmse_before": best_rmse,
        "absolute_improvement": improvement,
        "min_improvement": MIN_IMPROVEMENT,
        "max_relative_degradation": MAX_RELATIVE_DEGRADATION,
        "group_failures": group_failures,
        "reason": "Candidate passed all configured gates." if accepted else "; ".join(reasons),
        "created_at_utc": now,
    }
    if accepted:
        _write_json(
            args.best,
            {
                "experiment_id": args.experiment_id,
                "candidate_metrics_path": str(args.candidate),
                "candidate_record": candidate_record,
                "dataset_kind": candidate_manifest.get("dataset_kind", "unknown"),
                "metrics": candidate_metrics,
                "accepted_at_utc": now,
                "verdict": "accepted",
            },
        )
    _write_json(output, verdict)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    if not accepted:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
